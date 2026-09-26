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
| 4 | automatic rollback | two conditions that together excluded the only scenario it exists for |
| 5 | `_restore_config` | replayed a config through config mode — a *merge*, which cannot remove a line |
| 6 | `assert_rollback_provenance` | inspected only `no X` lines, so a synthesised non-negating line was never in scope |

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

### Number four, the strongest specimen

The first three each have a line you can point at. This one does not, and that
is what makes it worth recording separately.

Rollback is the net: a push that fails partway is exactly what it exists for.
It did not fire when a push failed partway. Two conditions, in two different
functions, written at different times:

```python
# the trigger, in PipelineRunner.run()
if on_failure == "rollback" and "deploy" in self.ctx.stages_completed:

# the target list, in _stage_rollback()
targets = [ip for ip, r in ctx.push_results.items() if r.get("ok")]
```

Read either on its own and it is defensible.

The trigger says *only roll back if we actually got as far as deploying* —
sensible, since stages 1–5 never touch the device and rolling back after them
would be noise. The flaw is that `stages_completed` records **successful**
stages, so the condition is false precisely when the deploy stage is the thing
that failed. It fires for a verify failure after a clean push. It cannot fire
for a push that died mid-stream.

The target list says *restore the devices we pushed to* — also sensible, and
the obvious reading of "we pushed to it" is `ok: True`. The flaw is that a
device whose `send_config_set` raised had commands going down the wire when it
gave up. It is not "a device we didn't push to". It is the **most** likely
device to be half-configured, and it was the only one the filter removed.

Neither is wrong about what it says. The defect lives in the **conjunction**:
one excludes the failing stage, the other excludes the failing device, and the
intersection they leave is empty for exactly one scenario — the scenario the
whole mechanism was built for.

### Why review does not find this one

For #1 the question "what makes this fail?" is answerable by reading four
lines. For #4 there is nothing to read: two correct functions, in two files,
neither referencing the other. The only way to see it is to ask the *outcome*
question rather than the *code* question:

> For each failure mode this mechanism exists to handle, trace the path and
> confirm it actually runs.

Not "is the rollback code correct" — it was. Not "is it called" — it was, from
the right place, under a guard that reads correctly. The question is whether
there exists an input for which it *executes*, and for the mid-push case there
was not.

This is the same test as the other three, phrased for a mechanism rather than a
function: **construct the scenario that triggers it; if you cannot, it is not a
safety net.** The cost of skipping that question here was a device left in a
half-configured state with the tool reporting only that the push had failed.

### What it cost, concretely

S4 ran for the length of one deploy with `description NSoT-managed b` on an
interface — a truncated, meaningless value that no store in the system
contained. The pipeline held an open connection to that device and reported a
Netmiko pattern timeout. Not "the device changed"; not "rollback attempted".
A human found it by going to look.

That is the compounding: the guard that would have repaired it could not fire,
and the report that would have revealed it did not exist. Neither gap is
visible from inside the other.

### Number five, where the docstring said it outright

```python
def _restore_config(conn, config_text: str) -> None:
    """Replace running config with the saved pre-change text via Netmiko config mode."""
    ...
    conn.send_config_set(lines, read_timeout=120)
```

The docstring says **replace**. `send_config_set` **merges**. Both statements
are on the screen at once, four lines apart, and they contradict each other.

This one is different from the first four in a way worth naming: the evidence
was not hidden in a seam, a conjunction, or another file. It was in the
function's own first line. The word "Replace" described what the author
intended; the body implemented what Netmiko does; nobody ever read the two
together, because reading a docstring *is* how you avoid reading the body.

The consequence is specific and it was about to be demonstrated live. IOS does
not print `no shutdown` in an up interface's running config — an interface is
up by default, so there is nothing to record. A pre-change snapshot of a
healthy interface therefore contains no line describing its up-ness. Replay
that snapshot after pushing `shutdown` and every line in it re-applies
successfully, `save_config()` runs, and the log reads `restored successfully`
while the interface stays down and the state survives a reload.

The planned demo was: shut an interface, watch verify fail, watch rollback
restore it. It would have produced a green rollback and a dead interface.

### Why a docstring is not a weaker signal than a test — it is a different one

The instinct after finding this is "the docstring lied". That is the wrong
lesson, because it suggests trusting docstrings less. The useful reading is the
opposite: **the docstring was the only correct statement of intent anywhere in
the system**, and the defect is that nothing ever compared it to the
implementation.

`send_config_set` merging is not obscure — it is the documented behaviour of
the most-used function in the library. The author knew what they wanted
("replace") and reached for the tool they already had. The gap between those is
exactly where this whole family lives.

> When a docstring states a property the body does not obviously provide, that
> is a claim awaiting a test — not a description.

The test that closes it is two lines and names the case the merge cannot
handle:

```python
def test_shutdown_is_undone_with_no_shutdown(self):
    undo = rollback_commands(["interface GigabitEthernet0/1", " shutdown", "exit"],
                             "interface GigabitEthernet0/1\n description old text\n")
    assert undo == ["interface GigabitEthernet0/1", " no shutdown", "exit"]
```

### Number six: a guard whose scope excluded the thing that went wrong

``assert_rollback_provenance()`` enforces the project's most important promise:
this tool never sends a command it did not derive from something it was asked
to do. It was written carefully, checks provenance rather than syntax, and has
a test asserting it raises.

It looked at lines starting with ``no ``. Only those.

A rollback also contains section headers and restored prior values, and neither
is a negation, so neither was examined. When ``rollback_commands()``
misclassified ``interface GigabitEthernet0/1`` as a setting and "restored" it
to ``interface Loopback0``, the guard saw a line that did not start with ``no``
and moved on. A synthesised command reached a live device through the check
written to stop exactly that.

This is subtler than #1–#5. The guard is not in the wrong place, it is not
handed the wrong input, and its logic is right. Its **scope** is narrower than
the property it is named for, and the gap is invisible unless you enumerate
what can legitimately appear in the thing being checked — which is a different
exercise from reviewing the check.

> A guard named for a property must cover every category of input that
> property ranges over. Enumerate the categories; a category nobody listed is a
> category nobody checks.

For a rollback there are exactly three: an inverse, a restored prior value, and
ancestry of one of those. Writing that list down is what makes the old
implementation obviously incomplete — and the list did not exist anywhere until
the defect forced it.

### The same defect, twice, from opposite directions

Worth noting together, because they were one bug in the product and two
different mistakes:

* ``rollback_commands()`` **re-derived** a classification the forward path
  already had. ``merge_commands()`` knew ``interface GigabitEthernet0/1`` was
  context — it emitted that line *because* a diff line sat under it. The
  rollback asked the question again, from key shapes, and got a different
  answer.
* ``assert_rollback_provenance()`` would have caught the resulting bad line if
  its scope had covered headers.

Two independent safeguards, both defeated by the same input, for unrelated
reasons. The fix is correspondingly two-sided: the classification now lives in
one function (``program_structure``) that both paths consume, and
``merge_commands`` asserts its own notion agrees with it — so a future change
to either fails loudly instead of the rollback quietly disagreeing.

> Where two paths must agree about the same fact, they must **share** the
> computation, not each compute it. Agreement by convention is agreement until
> someone edits one of them.

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

---

## Method, not code: a test written after the implementation encodes the implementation

Every other entry here is a defect in the product. This one is a defect in how I
was working, it happened four times in one week, and it is the most transferable
thing in the document — the product bugs are specific to this codebase; this is
not.

### The four

The rolled-back-intent block went through three wrong keys and the revert went
through one wrong shape. In each case a test existed, passed, and was useless.

| # | The requirement | What I implemented | What my test asserted |
|---|---|---|---|
| 1 | a rolled-back change must not be re-proposed | key the block on the intent **commit sha** | that a *new commit* lifts the block |
| 2 | same | key on a **content hash** of host_vars | that *editing a field* lifts the block |
| 3 | same | key on **program equality** | that a *different program* lifts the block |
| 4 | reverting undoes the rolled-back change | restore the **previous snapshot** | that reverting the commit *at HEAD* works |

Read the right-hand column on its own and every one sounds reasonable. Read it
against the left and none of them tests the requirement. They test the
mechanism. The mechanism was the thing in doubt.

### Why it keeps happening

Writing a test after the code puts you in the code's frame. You have just
decided that the answer is "compare shas", so the question you naturally write
down is "does it compare shas correctly?" — and it does, so the test passes, and
the passing test becomes evidence for a decision it never examined.

The tell is that all four tests were *true*. None was sloppy or wrong about what
it asserted. A sha-keyed block really does lift when a new commit lands. The
defect is that lifting on a new commit was never the requirement, and nothing in
the test's own frame could reveal that.

### What closed each one

Not better code review, and not more tests. In every case what closed it was a
test **specified in plain language from the requirement, before the fix
existed**:

> "an unrelated intent edit does NOT clear the block"
>
> "an unrelated edit that produces its own sent line"
>
> "unrelated commit on top → A undone, B kept"

Each of those sentences is a scenario, not a mechanism. None of them mentions
shas, hashes, fingerprints, containment, or diffs — and that is exactly why each
one survived the implementation changing underneath it. The sentence
"an unrelated edit does not clear the block" was written once and caught three
different wrong implementations in a row, including one I wrote *as the fix for
the previous failure of the same test*.

### The asymmetry that makes this cheap

Specifying the test first costs one sentence. Not specifying it costs a wrong
implementation shipped, or — in three of these four — a wrong implementation
that would have been shipped if someone had not asked the question in plain
language from outside the code.

There is a real distinction between two things that look identical in a test
file:

* **a test written from the requirement** — survives a rewrite of the
  implementation, because it never mentions it
* **a test written from the implementation** — is invalidated by a rewrite and,
  worse, passes through one

Both are green. Only one is evidence.

### The rule

> Write the assertion as a sentence about the world before writing the code that
> makes it true. If the sentence mentions how the code works, it is not a test
> of the requirement.

And the corollary, which is the part that actually bit here:

> A test written to close a failing test is at maximum risk of encoding the new
> implementation. The second fix for the same requirement deserves *more*
> suspicion than the first, not less.

Three of these four were second or third attempts.

### Worth recording honestly

In none of these four cases did I notice on my own. Each was caught by someone
reading the behaviour and asking a question from outside the implementation —
"does this handle the case where…". The value added was not expertise in this
codebase; it was refusing to reason in the code's frame. That is a role, and it
can be occupied deliberately: state the requirement, state the scenario, then go
and look at what the code does about it.

---

## The rule broken by its own author, in the section that states it

`docs/NSOT_PLAN.md` carries a design rule written during Phase 3c:

> A gate must be keyed on the property it claims to protect. Template fidelity
> protects against an untrustworthy renderer. Intent drift is the work, not a
> defect, and gating on the work means no work can ever be done.

Four paragraphs below it, the same section specified the template approval
fingerprint as **template hash + bound device set + a hash of each bound
device's host_vars**.

That third term keys the gate on the result of the work. A deploy changes the
device's captured configuration; the captured configuration is what the hash is
taken over; so a successful deploy revokes the approval that authorised it.

### What it looked like on real hardware

Run 3A stopped at its second step:

```
deployable: False
blocking:   ["template 'cisco_ios/base.j2' is not approved for this device"]

stored fingerprint   a7c85e85a207c52d
current fingerprint  9e0bdcf33fc37976
  s1: 1ed91501dfca55ab    unchanged
  s2: 1fe21b7db7570742    unchanged
  s3: ec058ccf8f66851b    unchanged
  s4: caae860616f18e6f → d5ebbe3e10899b42    CHANGED

template hash same?     True
bound device set same?  True
template still reproduces s4?  missing 0, extra 0, fidelity 100.0%
```

Everything the approval claims was still true. One interface description had
been deployed to s4 forty minutes earlier, and that revoked the template for
s1, s2 and s3 as well — three devices that had received nothing.

### Why this specimen is worth keeping

The other entries in this document are defects found in code. This one was
specified — deliberately, in a design amendment, by the person who a day later
wrote the rule it violates. It survived design review, implementation, a test
suite written around it, and an explicit approval step, because at every point
it reads as *more* rigour rather than less. "The approval records exactly what
was validated" is a sentence nobody argues with.

The tell is available without running anything, and it is the same question the
rest of this document keeps arriving at:

> For each thing this gate is meant to stop, and each thing it is meant to
> allow, trace whether it does. If a *successful* use of the system trips it,
> it is keyed on the wrong property.

A gate that fires after every success is not strict. It is noise, and its real
effect is to train the operator to clear it without reading — which leaves the
system in the state it would be in with no gate at all, plus a ritual.

### The correction

| | claim | revoked by | measured |
|---|---|---|---|
| approval | validated against **this device set** | template edit, device joining or leaving | once, recorded |
| `template_report` | reproduces **this device now** | nothing — recomputed | live, per device, every plan |

The second question was already being answered on every plan, by code that
already gated, and which names the offending lines. The approval fingerprint
was duplicating it in frozen form — and a frozen answer to a live question is
wrong the moment anything moves, which is the general form of the error.

Scheme 1 records are not silently accepted under scheme 2. A stored gate whose
meaning has changed is worse than no gate: it passes for a reason nobody
holds any more.

---

## Reading the evidence over the connection that just broke

Small, and worth recording because the reasoning generalises past the specific
bug — which was never reproduced.

`_capture_failure_state()` exists to answer the question an operator has after
a failed deploy: *what is actually on the device now?* It ran over the pooled
connection — the same session the push, the snapshots and the verify had used,
and therefore the same session that had just been through whatever went wrong.

On the first real rollback it returned:

```
Pattern not detected: '\^@' in output
```

`^@` is NUL. Netmiko was expecting a prompt string of NUL bytes, which means
`find_prompt()` had read garbage — a dead or desynchronised channel, not
malformed output. The connection pool *does* check liveness via
`is_alive()`, and `is_alive()` had returned true: it verifies the transport is
up, not that the channel is in sync.

### What was not established

The trigger. A fresh connection doing push-then-read reproduced nothing —
prompt intact before and after, 170 lines read back. Syslog interleaving was
ruled out (no `terminal monitor` is issued, and `logging trap critical`
excludes the `%LINK-5` notices), as were exec-timeout (the whole run was 107
seconds) and the management path (a different interface entirely).

One occurrence, plausible mechanism, not reproduced. Recorded that way on
purpose: naming a cause here would be a guess wearing the clothes of a finding,
and the next person would stop looking.

### Why it is worth fixing without knowing the cause

The argument does not depend on the trigger:

> A diagnostic path runs **only** when something has already gone wrong on the
> thing it is diagnosing. That makes it the path most likely to be handed a
> broken instrument, and its failure mode is losing the evidence.

A fresh SSH handshake costs nothing on a path that by definition only runs on
failure. Reusing the pooled session buys an optimisation in the one situation
where the optimisation is least likely to hold.

The second half follows from the same reasoning: if a *fresh* connection cannot
read the device, the pooled one is certainly no better, so it is dropped rather
than left for the next caller — and the next caller is the rollback.

### The part that worked

`device_changed` came back `None`, not `False`. The capture failed, and the
report said "unknown" rather than "unchanged". That distinction was written in
deliberately — *"an unreadable answer is not a clean bill of health"* — and it
is the only reason the failure was legible at all rather than an incorrect
all-clear sitting in a deploy report.

---

## Measuring before raising the number

A follow-up to the fresh-connection fix, and a small case of a habit worth
keeping: the failure-state capture was timing out, and the obvious response is
to raise the timeout.

Raising it first would have worked, and would have hidden which of two very
different things was happening.

### The measurement

```
idle connection:
  show running-config (10s)     5.49s   169 lines, ends with `end`   OK

after write memory:
  write memory                 11.85s
  show running-config (10s)    10.47s   ReadTimeout
  show running-config (10s)    16.44s   ReadTimeout
  show running-config (30s)    13.91s   169 lines                    OK
```

### What it distinguishes

Two candidate causes produce the same symptom:

* **an unanswered `--More--`** — `terminal length 0` not applied on that
  session, so the device waits forever for a keypress
* **a genuinely slow device**

They are told apart by what arrives, not by how long it takes. Paging returns
**partial** output, cut mid-config at the pager prompt. Here the output was
complete every time it arrived — 169 lines terminating in `end` — and the same
command on an idle connection finished in 5.5s. A session missing `terminal
length 0` would fail identically regardless of device load.

So: a slow device, and specifically one made slow by `write memory`.
`_push_via_netmiko()` saves immediately after every push, NVRAM on this
platform is emulated on disk, and the box stays slow for tens of seconds
afterwards. The capture runs a few stages later — sometimes inside that window,
sometimes not, which is exactly why the first occurrence looked intermittent.

It also established that the earlier NUL failure and this timeout were
**different faults**. The connection fix did not fail to solve this one; it
converted an unreadable desynced session into an honest timeout, which is what
made the measurement possible at all.

### Why it is a setting

The number that works here is a fact about one containerlab vIOS-L2 with
emulated NVRAM. A real 9300 writes NVRAM in under a second; a busier or slower
platform could be worse than this one. Hardcoding 120 would be the same
category of mistake as the hardcoded TFTP server address and the reference
topology in the AI prompts — a local truth compiled into code that travels.

`nsot_config_read_timeout`, default 120, minimum 5. The default is generous
rather than tuned, because the cost of being too generous is waiting longer on
a path that only runs after a failure, and the cost of being too tight is
losing the evidence.

> When a limit needs raising, measure first — the measurement usually
> distinguishes two causes that the raised limit would have made
> indistinguishable. Then make it configurable, because the number you measured
> is a fact about the thing you measured.

---

## What the NSoT found out about the network, not about itself

Everything else in this document is a defect in the tool. This is the first
thing the tool established about the **network**, which is the point of
building it.

Onboarding r2 (a C8000v) after s4 (a vIOS-L2) surfaced a difference nobody had
written down:

```
s4:  user_admin_secret     kind=hash        rotatable=False    enable secret 9 $9$…
r2:  user_admin_password   kind=plaintext   rotatable=True     username admin … password …
     snmp_community_ro     kind=plaintext   rotatable=True
```

Two devices in the same lab, administered the same way, storing the same
credential in two different forms. s4 holds a type-9 hash, which is salted and
cannot be regenerated — the extractor records the hash string verbatim and
marks it `secret_kind: hash` precisely so a future rotation skips it. r2 holds
a plaintext password, which rotation can and should change.

Neither is wrong. They were configured at different times, probably by
different commands, and no running-config diff would have shown it as a
difference — both devices look internally consistent, and the two lines are not
the same line.

### Why this is the interesting kind of finding

It is not a drift, a misconfiguration, or a bug. It is a **fact about the
network that only became visible once the network was modelled**. Reading nine
running-configs would not surface it; you would have to already suspect it and
go looking. The extractor surfaced it as a side effect of answering a different
question — what secrets does this device have, and can they be rotated?

That is the argument for a source of truth, stated more concretely than "single
pane of glass". The value is not that the data is in one place. It is that
putting it in one place makes per-device variation legible as variation rather
than as nine separate normal-looking configs.

### The Part 2 consequence

Rotation will treat these two devices differently, and correctly: r2's password
can be rotated, s4's hash cannot. A rotation implementation that assumed
uniformity — "rotate the admin credential on every device" — would either fail
on s4 or, worse, "succeed" by replacing a hash with something the device then
refuses to authenticate against.

The `secret_kind` distinction was built in Phase 3a for a reason argued from
first principles (a salted hash cannot be regenerated). This is the first
evidence that the reason is *live* in this network rather than hypothetical.

r2's plaintext password is also, separately, worth fixing. That is an operator
decision the NSoT now makes askable.

---

## A tag that claimed more than it measured, and the relabel

`baseline/20260921T015446Z` was created by batch 4 after deploying to **three
of nine** devices. The tag asserts *the network looked like this*. Six devices
were never contacted, never read, and never verified — their goldens in that
commit are whatever the last save left there, which may or may not still match
the device.

It was not a bug in the sense of a wrong line of code. `save_golden` created a
baseline when one call changed more than one device, which was a reasonable
rule right up until "a batch is one call" made a three-device batch look like a
network-wide event.

The reason it mattered more than it looked: the Baselines panel lists every
`baseline/*` as a **"network-wide restore point"**, and restore is the
demonstration of the whole golden-config objective. The tag would have sat in
the headline feature, offering to restore a network state that nobody had
established.

### The relabel

```
batch/20260921T015446Z    created at 25d91167, the same commit
baseline/20260921T015446Z deleted
```

The commit is untouched — it is accurate history of what was deployed. Only the
claim changed. `baseline/20260920T212325Z-migrated` stays: all nine devices,
and the goldens at that commit *are* the captures they were taken from.

### The rule that replaced it

A baseline is now **earned by measurement**:

* every targeted device succeeded, **and**
* the whole inventory was targeted, **and**
* each device's post-deploy capture equals what was pushed to it

True by observation rather than by category — the same principle as
`device_changed` reporting `None` rather than `False` when a capture fails.
This also means an *additive* re-apply can earn a baseline if it happens to
leave no residue, which ruling it out by mode would have understated.

### The general shape

> A label that asserts a property must be issued by something that measured
> the property, not by something that observed a correlate of it.

"More than one device changed" correlates with "this was a network-wide
operation" until batching breaks the correlation. Every one of these is fine
until the thing it stands in for moves.

---

## Making a rule unrepresentable after documenting it twice failed

`interface Loopback0` and `interface Loopback1` both reduce to the command key
`interface`. Section headers are not settings, and treating them as settings
produced three separate defects:

1. a rollback "restoring" `interface Loopback0` to `interface Loopback1`, which
   reached a live device
2. `ip mtu 20000` matched against `ip address 10.255.1.24 255.255.255.255`
3. a diff reporting a *replace* between two different interfaces

The rule was written into a docstring after (1) and into a second docstring
after (2). (3) was written **by the same author, the same day, in a new
function**, about twenty minutes after committing the note explaining (2).

### Why documentation did not work here

The mistake is not one of knowledge. Each time, the code was written by someone
who had just explained the rule. The failure is that **"compare these two
config lines" is a natural operation to write**, and it stays natural right up
until one of the lines is a header — which is a property of the *data*, not
visible at the call site.

A docstring addresses the reader who is already looking at the function. It
does nothing for the author of a new function two hundred lines away who is
solving a different problem and reaches for the obvious helper.

### The fix: change what the function accepts

```python
class Leaf(NamedTuple):
    line: str
    chain: tuple

def _command_keys(leaf) -> tuple:
    if not isinstance(leaf, Leaf):
        raise TypeError("_command_keys takes a Leaf, not a line. …")
```

`Leaf` values are produced only by `program_leaves()` and `config_leaves()`,
both of which exclude headers by construction. Passing a raw line is now a
`TypeError` at the call site, immediately, in the author's own test run.

This is the same move as `resolve_identity()` losing the ability to mint. In
both cases the previous fix was "be careful in the right place", and in both
cases the next author was careful in a different place.

> When a rule is broken a second time by someone who knows it, the rule is in
> the wrong place. Move it from the documentation into the type, the signature,
> or the call graph — somewhere the compiler, the interpreter, or the test run
> enforces it without anyone having to remember.

A regression test also asserts, by scanning the module source, that every call
site passes a `Leaf` — because the type check catches a raw *string*, and the
remaining hole is someone constructing a `Leaf` around a header by hand.

---

## A whole function deleted, and 1133 tests passed

The worst defect in this stretch was not subtle. `_deploy_one()` — the only
function in `routes/deploy.py` that opens a connection to a device — was
deleted outright in commit `061158c`, and nothing noticed for three commits.

```
da8d7d4: _deploy_one defined = 1
061158c: _deploy_one defined = 0     ← deployed to the NMAS
7814ae0: _deploy_one defined = 0
```

### How it happened

An edit applied as a slice replacement:

```python
s = s[:s.index("def _baseline_earned")] + new_tail
```

`_baseline_earned` was the intended target. `_deploy_one` sat *after* it in the
file, so it went with the tail. The edit was mechanically correct for the
function it was aimed at and silently destructive for the one behind it.

### Why the suite did not catch it

Every test in `test_deploy_contract.py`, `test_deploy_safety.py` and
`test_deploy_batch.py` exercises the *pieces* `_deploy_one` calls —
`prepare_for_deploy`, `merge_commands`, `assert_merge_only`, the pipeline, the
batch runner — because those are the parts with interesting behaviour. Nothing
called `_deploy_one` itself, because calling it means standing up a pipeline
and a connection. So the function that stitches all the tested pieces together
was the one piece with no test, and deleting it changed no test's outcome.

It reached the live host and sat there, because everything done since was a
read-only preview. A preview never reaches the deploy path. The first live
re-apply would have been an `AttributeError` mid-batch.

### The general shape

> A test suite that covers every component and not the wiring will pass with
> the wiring removed. Component coverage is a statement about the components.

This is the mirror of *"a test written after the implementation encodes the
implementation"*: these tests were written around a design, faithfully, and
the design's own connective tissue was invisible to them.

### The countermeasure

Cheap and structural, in `test_deploy_contract.py`: parse each route module's
AST, collect every private name it *calls*, and assert each is defined. It
fails in 0.1s with the function removed, and it costs nothing to maintain
because it derives the expectation from the source rather than restating it.

The class of bug — "the name is gone and nothing looks it up until runtime" —
is the cheapest class there is to catch and the most embarrassing to ship, so
it gets a test of its own rather than relying on some other test happening to
import the right thing.

### The second-order lesson, which is the real one

This is the third time in this project that a *scripted* edit has destroyed
code: `modules/nsot/deploy.py` grew to 2.4MB of recursion, a pruning script
removed test class headers, and now this. Each time the script was correct
about what it was changing and careless about what it was adjacent to.

> Anchor edits to the text on **both sides** of the change. An edit that says
> "replace from here to the end of the file" is asserting something about every
> line after it, usually without having looked.

---

## Restoring the device without restoring the intent

Item 1 gave the re-apply button an honest label. Item 2 is what makes the
button's effect survive the next plan.

### The failure it prevents

Re-applying a ref writes the ref's configuration onto the device. It does not
touch `host_vars/`. So a moment later:

* the device is at the ref
* committed intent still describes the state the operator just undid
* the next template plan offers to put that state back

The operator sees a "drift" they created by pressing restore, and the source of
truth is arguing with the network about a change the source of truth won.
Restoring half of a two-part state is worse than restoring neither, because it
looks like it worked.

### Device and intent are one unit per device

Not one unit per batch. A device whose push failed keeps today's intent — it
never reached the ref, so the ref's intent would describe it wrongly in the
other direction. `_write_restored_intent()` writes only for devices whose
outcome is `DEPLOYED`, and the write lands in the **same commit** as that
device's golden capture, because two commits means a window where the pair
disagrees and a crash makes that permanent.

For the window that remains — between the push landing and the batch commit —
the intent is staged to `.nsot/staging/restored_intent/`, the same treatment
the post-deploy capture already gets.

### A forward commit, never a rewind

The ref's `host_vars` are written into the working tree as today's intent and
committed forward. History between the ref and now is untouched, so the intent
that was replaced stays reachable by `git log -- host_vars/<device>.yml`.
Nothing is reset, reverted, or force-pushed.

### Verbatim, which turned out to need a fix

The ref's `host_vars` are re-committed **byte for byte**, not re-serialised
from the parsed dict. A round trip through the parser normalises key order and
drops comments — a change the operator did not ask for, landing in a commit
labelled "restore".

That required fixing a read. `git()` in `repo.py` returns `proc.stdout.strip()`,
which is right for a sha and wrong for file content: it silently drops the
trailing newline, so writing the result back produces a one-byte diff. Added
`git_raw()` and pointed `RefSource.read()` at it.

> Same shape as the porcelain-offset bug: a helper that tidies output for
> display, reused where exactness is the requirement.

### Un-onboarding is an outcome, not a default

A ref that predates a device's onboarding has no intent for it. Three options:

1. restore the config, leave today's intent — the fight-itself state
2. restore the config, delete today's intent — silently un-does a human review
3. skip the device

The default is **3**. Deleting reviewed intent is not something an operator
should get by pressing the same button that restores a config, so it is opt-in
per device, named in the dialog, and described as what it is: recoverable from
git history, but an un-doing of the onboarding review.

The opt-in re-runs the **preview** rather than going straight to apply. A
skipped device has no command list and no confirm hash; sending it to apply on
the strength of a second dialog would be confirming commands nobody was shown,
which is the thing the confirm hash exists to prevent.

### The guard that had to widen

`save_golden()` returned early on "no content changed", judged purely on
`golden/`. A restore to a ref a device *already matches* changes no golden and
still moves that device's intent — so the intent was written and never
committed, leaving a dirty working tree in the live repo and a restore with no
record.

The guard now asks about the whole commit: golden content, or anything
`extra_paths` staged. The original property is kept by a test that asserts a
call with neither still creates nothing.

---

## A baseline tag earned by measurement, on either path

The tag rule, finished:

> **A skipped device counts only if it was MEASURED.**

Which replaces "every targeted device succeeded" for restore with **every
inventory device measured equivalent to the ref, whatever path got it there**.

### What that forced

A device with nothing to send used to return `DEPLOYED — nothing to change`
and contribute no capture. But "nothing to send" was decided by diffing the ref
against a **stored** capture, and a stored capture is a record of an earlier
moment, not evidence about the device now. Counting that device toward a tag
that claims "the network is at this ref" is inference wearing a measurement's
label.

So `_measure_unchanged()` reads the device anyway — a read, nothing sent — and
hands the capture to the batch like any other. The device is now measured, and
counts. If the read fails, it contributes nothing and the tag is declined; an
unreachable device is not a matching device.

### The consequence worth stating plainly

**Residue denies a restore baseline, by design.** Merge-only cannot remove a
line the device has gained and the ref does not mention, so after a re-apply
the network demonstrably is not back at the ref. The tag says so. Mode A can
therefore earn `baseline/` only when the drift it re-applied was purely
additive — which is exactly the honest answer, and it is reached by measuring
rather than by a rule about which mode ran.

The two claims stay different, which is the point:

| path | claim | how it is decided |
|---|---|---|
| deploy | this commit's goldens are the network | coverage: every inventory device is in the commit |
| restore | the network is back to the ref | content: every inventory device read back and compared |

A deploy baseline is not measured against content, because the goldens in that
commit *are* the post-deploy captures — measuring them against the render would
report every unmodelled construct as a difference and deny a whole-fleet deploy
a tag it had earned.

---

## The corpus had the right shape; the comparison could not see it

The single most instructive defect in the project. For three weeks the fleet
reported **100% modeled, 100% round-trip fidelity, zero unmodeled constructs**
across nine devices. Three of those devices were wrong, and the number was
produced by the thing that was wrong.

### What was broken

`cisco_iosxe/base.j2` rendered r3, r4 and r5 like this:

```
 address-family ipv4
 no neighbor 2001:DB8:51::2 activate
 exit-address-family
 !
 address-family ipv6
 exit-address-family
 neighbor 198.51.100.1 activate      <- outside every family
 network 2001:DB8::/32               <- an IPv6 prefix, outside ipv6
```

Every network and neighbor activation was hoisted out of its address-family to
the top level of `router bgp`. A deploy would have sent an IPv6 prefix where
IOS does not accept one, and `no neighbor … activate` where it changes a
different family.

### Why nothing caught it

`parsers.base.split_blocks()` appends **every** indented line to one flat
`children` list regardless of depth — correct for a parser, which wants a block
and its body. `roundtrip._sections()` was built on it, so a two-level block was
compared as one level. Every line was present on both sides. Score: 100%.

Three properties conspired, and each is worth naming separately:

1. **Parse and render flattened symmetrically.** The parser threw the nesting
   away and the template re-emitted the same flat list, so the two sides agreed
   with each other while both disagreed with the device. A round-trip test
   compares a system against itself; two mirrored bugs cancel.
2. **The corpus was fine.** This is the part worth dwelling on. The instinct
   after a miss like this is "we need a fixture with BGP address-families" —
   but `tests/fixtures/configs/fleet/` had carried them from the day r3–r5 were
   added, and `r5.cfg` is a full dual-stack PE. Adding more fixtures would have
   changed nothing. **Test data cannot compensate for an instrument that cannot
   measure.**
3. **There was a named test, and it asserted the defect.**

```python
def test_bgp_address_families_on_r3_r4_r5(self):
    bgp = report["host_vars"]["routing"]["bgp"]
    assert any("address-family" in s for s in bgp["settings"])
```

That asserts the address-family *header* is an ordinary setting — which is
exactly the flattening. Written after the implementation, it encoded the
implementation, and it did so under a name that made the construct look
covered. Anyone auditing would have read "BGP address families: tested" and
moved on. **A test named for a feature that checks for a substring is worse
than no test: it spends the name.**

### Where the right answer already lived

`deploy._section_chains()` has been depth-aware since Phase 3c, and its
docstring names this exact hazard:

> A partial chain is worse than none: sending `neighbor … activate` after only
> `router bgp 65001` applies it to the wrong address family, silently and
> successfully.

So `merge_commands()` — the function that decides what goes on the wire — knew.
Running it against each device's own golden produced 7 spurious lines for r3
and r4 and 14 for r5. **The tool could compute the right answer and
simultaneously report that there was nothing to compute.** Two components held
opposite models of the same config and nothing compared them, because the
comparison *was* one of the two.

### How it was actually found

Not by a test, and not by the metric. By a human asking for a **named-item
check**: "report what the extraction actually modelled for BGP address-families
and neighbors." The answer came back `address_families=0` on a device whose
config plainly has two, next to a coverage figure of 100%. The contradiction
was only visible because someone asked the model to state *what* it had
modelled rather than *how much*.

> A percentage is a claim about a measurement. Ask what was measured, in the
> vocabulary of the domain, and an instrument that cannot see a construct has
> to say so.

### The fix, and the two regressions it introduced

`modules/nsot/sections.py` now holds the indentation→ancestry algorithm alone,
and `_sections()` keys on a line's full container path
(`router bgp 65002 > address-family ipv4`). Normalisation deliberately stays
with the caller — the filters in `normalize.py` are four different jobs, and
folding one in would have made this the fifth place that decides which lines
count.

Making the measurement stricter broke two things that had nothing to do with
BGP, and both are the same mistake in miniature — *a change meant to add depth
quietly added a rule*:

* the global scope became an ordered section, so every device reported one
  reordered section named `""`;
* the global scope counted as a matched *section*, so a wholly unknown config
  scored 16.7% instead of 0.

Both are now pinned by tests. The general lesson: when you sharpen an
instrument, the first thing to check is what it now says about the cases that
were already correct.

### The second defect, found because the first one needed fixing

Landing the BGP fix meant editing `templates/_common.j2`, which holds the
routing, interface and service macros for **both** platforms. `template_hash`
hashed only `base.j2`. So editing the shared macros would have changed what
every template renders while leaving `cisco_ios/base.j2` approved for s1–s4 —
a gate certifying a template on the strength of a hash of a file that did not
change.

Same shape as the round-trip metric, found three hours apart: **a gate that
measures less than its claim.** An approval says "this template reproduces
every bound device", and a template is `base.j2` plus everything it imports.
The fingerprint now covers the whole import closure, path-labelled so moving a
macro between files changes the hash even when the total text does not.

### Revocation as a record

`approval.revoke()` popped the record, which made a withdrawal indistinguishable
from "never approved". Both block a deploy, so the gate was never wrong — but
an approval is withdrawn for a *reason*, and deleting the record throws the
finding away. It now requires a reason and writes a tombstone carrying it,
refused by `is_approved()` **first**, ahead of every computed check. A test
forces the scheme and fingerprint to agree that the template is fine and
asserts the revocation still stands.

> A decision recorded by a person must not be overturnable by a computation
> that runs afterwards.

---

## A fix that shipped, passed its tests, and protected almost nothing

The outbound-redaction work is the clearest example in the project of a change
that was *correct*, *tested*, *reviewed* — and very nearly useless.

### What was claimed

`31bca0f` added redaction at the provider boundary. The commit message was
accurate about the mechanism: one choke point before `messages.create()`, whole
-token matching, longest-secret-first, degrades honestly when the store is
unreadable. Thirteen tests, including one driving seven different tool-result
shapes and asserting on what the client receives. Verified by mutation:
un-redacting `messages` failed the test.

Everything in that paragraph is true, and the leak was still open.

### What was actually true

Two defects, neither visible from the code or the tests.

**1. The length floor excluded nearly everything.** Redaction skipped values
under 8 characters, on the sound reasoning that redacting `RO` would corrupt
every config while protecting nothing guessable. Measured against the live
credential store afterwards:

```
template secrets: 18 total, floor is 8 chars
  9 × snmp_community_ro      6 chars   NOT redacted
  5 × user_admin_password    7 chars   NOT redacted
  4 × user_admin_secret     32 chars   redacted
UNDER THE FLOOR: 14 of 18
```

The four covered were the type-9 hashes — the only secrets that were *already*
safe, being salted and unrecoverable. Every value that actually mattered was
one or two characters below the line.

**2. Device credentials were collected as ciphertext.** The helper decrypted
`devices.csv` rows with `secrets_store.decrypt_value()`, which returns anything
lacking its own prefix **unchanged**. CSV fields use raw Fernet. So the
redactor was searching payloads for 100-character `gAAAAA…` strings that no
device will ever echo. Device passwords were not redacted at all.

Both were found by one question — *how many stored values fall under the
floor?* — asked only because a reviewer asked it. Neither would have been found
by more tests, because the tests supplied their own fixtures: every test secret
was comfortably over 8 characters and stored through the prefixed path. **The
fixtures were healthier than production.**

### The generalisable lesson

> A guard with a threshold is a claim about the data on the other side of it.
> The threshold was chosen by reasoning about what *could* be a secret; nobody
> measured what *was*.

This is the same shape as the round-trip metric that could not see nesting: an
instrument that was right about its own logic and wrong about the world, giving
a confident number either way. The countermeasure is identical — **measure the
corpus, not the mechanism** — and it is worth noting that the project had
already learned this lesson once, three commits earlier, and still shipped it
again in a different costume.

### What actually closed it

`efb007e`, with **positional** redaction: mask whatever occupies a secret's
syntactic slot — `snmp-server community <X>`, `username … password|secret <X>`,
`enable secret <X>`, `key-string <X>` — regardless of length and regardless of
whether the store has ever seen the value.

Position is the discriminator length never was. `community X RO` tells you X is
a secret whatever X is, and it covers what value matching cannot reach by
construction: devices never onboarded, lists never extracted, a password typed
into a chat message.

Fleet result, measured rather than asserted: **0 unmasked secret-position lines
across all nine devices**, against 110 secret occurrences before.

The residual is the useful part of the result. `description eBGP to r5 Gi2 -
simulated public` keeps the word "public", because the community is already
masked where it *is* a community, and a redactor that mangles prose is one
that gets turned off. The floor was not wrong — it was answering a different
question than the one that mattered.

> **Do not date the fix from the commit that described it.** The leak was open
> from `31bca0f` to `efb007e`. A changelog that credits the first is telling
> the story of the intention, not of the network.

---

## "I tested it" and "it is running" are different sentences

Twice in one session I reported a verification that was real, against code that
was not deployed.

**First time.** Redaction looked broken against the live fleet — 110 secret
occurrences before, 106 after. The overlay used to run live checks is built
with `git archive HEAD`, which takes the last *commit*; the positional
redaction under test was still uncommitted. The measurement was of the previous
implementation, and I nearly reported a working fix as a failure.

**Second time, the opposite direction.** After adding
`require_person_for_reveal`, I checked the rule against live settings through
the overlay, saw `reveal: False`, and wrote that this was "already enforced"
by the running build. It was not. The setting was **unset** in
`user_settings.json`, so its value came from `DEFAULTS` — which is *code*. The
overlay was running the new code; the app was running the old. A service could
still have revealed every secret in the store, and I had just told the operator
it could not.

### Why the second one is worse

The first produced a false negative I would have chased. The second produced a
**false assurance about a security control**, which nobody chases, because it
says everything is fine.

The trap is specific: a setting absent from the settings file takes its value
from the defaults in the source. So "this comes from settings, not code" —
which is what I told myself — is only true for settings that have actually been
*written*. For everything else, changing the default **is** a code change, and
it ships when the process restarts, not when the file is edited.

### The rule

> A claim about the running system has to be measured against the running
> system. Anything else is a claim about a build.

Concretely, for this project:

* the overlay (`/tmp/nsot_run`) tests **code**, including uncommitted code if
  copied in deliberately — never what the deployed process does;
* `git log -1` in the checkout says what was *pulled*, not what is *loaded*;
  the process start time versus the pull time is the thing to compare;
* a gate's effective value is `user_settings.json` **if the key is present**,
  and the running build's `DEFAULTS` otherwise — and only the first survives a
  restart of older code.

The check that actually settles it is the one the operator asked for: hit the
real endpoint, through the real path, and read what the process says about
itself. `GET /identity/status` exists for exactly that, and it answered in one
request.

---

## Two claims that looked like one: what a device runs, and what it will boot

The NSoT golden repo answers *"what is this device running?"* with a commit,
a tag and a diff. It was easy — and wrong — to read that as also answering
*"what will this device be after a rebuild?"*

Containerlab nodes are ephemeral. `write memory` writes the **container's**
NVRAM; `containerlab deploy --cleanup` boots every node from startup-config
files on a different host entirely. Nothing connected the two. The config
persistence pipeline (`docs/ARCHITECTURE.md`) closes that gap, and its first
automated runs surfaced two things worth recording.

### 1. A latent rebuild failure nobody could have seen

The first automated run persisted an already-broken pair of startup files.
`s1` and `s2`'s files dated from 15 September and lacked `vtp mode transparent`
and the VLAN 10/20/30 definitions. With `--cleanup` wiping `vlan.dat`, a
redeploy would have brought both switches up with **undefined VLANs**, and
therefore dead SVIs and dead VRRP on every group they carry.

Nothing was wrong on the running devices. Nothing was wrong in the golden repo.
The defect existed only in the *third* copy — the one that decides what happens
after a rebuild — and only a rebuild would have revealed it.

> A stale artifact is not detected by looking at the systems it was derived
> from. It is detected by regenerating it and comparing, which is what a
> continuous sync does and an occasional one does not.

This is the argument for continuous over occasional in a sentence: the files
were wrong for six days, and the only reason it was not an outage is that
nobody happened to redeploy.

### 2. NMAS deploys had never reached a startup file

The same run also persisted this week's NMAS work — the `r2`/`s3`/`s4`
loopback descriptions from batch 4 and the smoke tests. **No NMAS deploy had
ever reached a startup file before.**

Every guarantee built in Phases 2 and 3 — one call one commit, the confirm
hash, merge-only, rollback, the earned baseline — is a guarantee about *what
the device is running and what was recorded about it*. All of it was true, and
all of it would have evaporated on `--cleanup`.

> "The source of truth records what devices run" and "the devices will come
> back that way" are different claims. A system that makes the first one very
> rigorously can still be silently failing the second.

That is not a flaw in the golden repo — it is a boundary of it, and the
interesting part is how long the boundary went unstated. It took building a
pipeline *outside* the repo to notice that the repo's central claim had an
unspoken "…until the next rebuild" attached to it.

### The shape both share

Both are **third-copy problems**. The device has one copy, the NSoT has a
second, and the boot-time artifact is a third that neither of the first two can
see. Anything derived-and-stored has this property, and the countermeasure is
the same in each case: regenerate it on a schedule, validate it mechanically,
and make a validation failure refuse to publish rather than publish something
plausible.

The truncation guard in that pipeline is the same lesson again, one level down.
Every older check — `end` count, `hostname` count, cert/banner/mgmt leakage,
missing `no shutdown` — passed on a **simulated truncation at the first
`router` block**, on all nine devices. Each check asked "is what I am looking
at well-formed?" and none asked "is it all here?". Counting blocks in and
blocks out refused all nine.

---

## Where the real security boundary turned out to be

Demonstrating out-of-band recovery for the credential rotation produced a
finding about the lab that had nothing to do with credentials.

The recovery path is the qemu serial console inside each container:

```
ssh dmarchak@10.0.0.210
docker exec -it clab-rcn-lab1-r2 telnet localhost 5000
```

It works. It reaches `r2>` with **no authentication at all** — no username, no
password, no prompt. And because none of these devices has an `enable secret`,
typing `enable` at that prompt yields **privilege 15**.

Measured again before stage 2, on both platforms, because the operator-facing
half of this had been left implicit. The console lands at privilege **1**:

```
s3> show privilege   ->  Current privilege level is 1
s3> enable           ->  s3#          (no password prompt)
s3# show privilege   ->  Current privilege level is 15
```

`r5` behaves identically, so this is the IOSv and vIOS-L2 behaviour rather than
anything per-device. The security conclusion is unchanged — unauthenticated
privilege 15 is one word away — but the *mechanism* is what somebody follows
under pressure, and the confirm screen had been printing the `docker exec` line
without the `enable` step. An operator recovering a locked-out device would
land at `s3>`, find they cannot configure, and reasonably conclude the recovery
path was broken. It now prints both steps.

So the device's `username admin privilege 15 …` line — the thing this whole
item exists to strengthen — protects the *SSH* path and nothing else. Anyone
who can reach the serial console already has full configuration access to
every device in the lab, before and after any rotation.

### What actually guards it

```
SSH key to 10.0.0.210  →  membership of the `docker` group  →  serial console
                                                            →  privilege 15
```

Two OS-level controls, neither of which is a network credential. Rotating
router passwords from cleartext to scrypt is still worth doing — it removes
five live secrets from git history — but it should be described accurately:
**it hardens one path into the devices, not the devices.**

### The general shape

> A credential is only a boundary where it is the *only* way in. Before
> hardening one, enumerate the others — otherwise the work produces a real
> improvement and a false sense of how much.

This is the same error as reporting reachability from inside the same /64: a
test that exercises one path and a conclusion drawn about all of them. It is
easy to make because the path you are working on is the one you are looking at.

### The fix, and why it belongs to Part 2

Configuring `enable secret` closes it: the console would still reach `r2>`
unauthenticated, but privilege 15 would need a secret. That makes the console a
read-only diagnostic rather than an unauthenticated root shell — and it creates
a second credential per device, which then becomes a **Part 2 rotation target**
with exactly the same machinery (`set_and_capture_hash`).

Worth noting the ordering trap: adding `enable secret` *before* the console is
proven as a recovery path would remove the recovery path for the rotation that
adds it. The console has to stay open until the rotation work no longer depends
on it.

## The mechanism was right; the verdict was about the wrong thing

The first hardware run of `set_credential` was against r2, with the serial
console open in a second terminal. Everything the design was built to get right
worked. The state machine and the lockout defence both behaved exactly as
specified — on hardware, against a real device:

- the original session opened and was **proven** with a read before anything
  was pushed;
- the new `username admin privilege 15 algorithm-type scrypt secret …` line was
  **accepted** by the device;
- the verify failed, so the tool **reverted** on the still-open original
  session — and the console confirmed the original line back in the running
  config, with the NMAS still able to log in.

The run then reported `REVERT_FAILED` and printed **"THE DEVICE MAY BE LOCKED
OUT — recover on the serial console"**.

Nothing was locked out. Nothing was even asked.

### The defect

`verify_new_credential()` built a device dict carrying the **plaintext** new
password and handed it to `with_temp_connection()`, which Fernet-decrypts
whatever it is given because every other caller passes an inventory row. The
decrypt raised `InvalidToken` **before a socket was opened**. The revert's
re-proof took the same path with the original password and failed the same way.

So the sequence was: push (worked, on hardware) → verify (failed locally) →
revert (worked, on hardware) → re-proof (failed locally) → `REVERT_FAILED`.

Two local exceptions, three feet from each other, were rendered as a statement
about a device that was fine the entire time.

### What made it worse than an ordinary bug

The failure mode was **not** that a working thing was reported broken. It was
that the most alarming message in the system — the one that exists to send a
person to a serial console at speed — was produced by code that never contacted
the device. A message like that is a resource: it is worth something precisely
because it is rare and trustworthy. Producing it from a local `except Exception`
spends that.

And the error was unfalsifiable from the outside. "The device may be locked
out" is not a claim the reader can check; it is a claim *about* the reader's
inability to check. Had the console not been open, the honest next action would
have been an out-of-band recovery on a device that needed nothing.

### Why the tests did not catch it

The test fixture monkeypatched `cr.verify_new_credential` **wholesale**, feeding
`rotate()` a queue of verdicts:

```python
monkeypatch.setattr(cr, "verify_new_credential",
                    lambda d, u, p: state["verify"].pop(0))
```

Every test of the five states passed, because the *sequence* — push, verify,
revert, commit — was real and correct. The one thing never executed was the
construction of the dict handed to Netmiko, which is the only place the bug
lived. The seam was drawn above the defect.

This is the same shape as [a whole function deleted, and 1133 tests
passed](#a-whole-function-deleted-and-1133-tests-passed) and the overlay that
[proved what the code would do, not what the process
did](#i-tested-it-and-it-is-running-are-different-sentences): a test that
exercises the part you were thinking about and stops exactly where the part you
weren't begins. A mock is a claim about where the untrusted world starts. Put
it in the wrong place and the tests verify the map.

### The fix

1. **`verify_new_credential()` connects directly**, through `ConnectHandler`
   with the plaintext it was given. It never passes a plaintext value to
   something whose contract is to decrypt.
2. **Every result carries `attempted`.** An authentication refusal or a
   timeout is a verdict *the device produced* (`attempted: True`). A local
   fault is not (`attempted: False`). `classify_failure()` identifies **both**
   sides positively, by exception name, rather than defaulting into either.
   An unrecognised name resolves to `attempted` — and says so in the reason —
   because the two errors are not symmetrical: a false lockout warning costs a
   console trip, while a false "local fault" leaves a device that may really
   be unreachable without one. The quiet outcome has to be earned.
3. **Inconclusive is retried, not acted on.** `verify_with_retry()` returns a
   verdict immediately and retries only local faults — which is free, because
   the original session is still open. The device is never reverted on the
   strength of a result that says nothing.
4. **A sixth state.** `REVERT_FAILED` is now reserved for the device being
   asked and refusing. `REVERTED_UNPROVEN` says the original was re-sent and
   the proof could not run, and states explicitly that this is *not* evidence
   about the device. Only the first may mention a lockout.
5. **The regression is pinned as the rule, not the symptom.** One test drives a
   full rotation with `with_temp_connection` monkeypatched to raise, so the
   verify path may not reach it by any route.

The new tests mock at the **Netmiko boundary** — a fake router that accepts
exactly one password at a time, learns a new one from the line the push sends,
and hashes it in its running config the way IOS does. Re-introducing the
original defect fails **16** of them, including four that had passed against
the stubbed verdict queue.

### The general shape

> A verdict about a remote system requires having asked it. A local failure is
> evidence about this process and nothing else — and the louder the message it
> produces, the more carefully that distinction has to be enforced.

Worth separating two things the run proved, because they point in opposite
directions. The **lockout defence works**: hold the original session, push,
verify on a fresh connection, revert on the held session. That is the part that
is hard to get right, and it was right, on hardware, on the first attempt. The
**reporting** was wrong in a way that would have sent a person to a console for
nothing. Designing the dangerous path carefully and the description of it
casually produces a system that is safe and untrustworthy at the same time —
and the second one is what people act on.

## The fix that needed its own fix, found by refusing to simulate it

Connecting directly in `verify_new_credential()` removed the decrypt defect and
created a second one: a **second set of ConnectHandler parameters**. Five sites
in the codebase built those kwargs independently and agreed only by
coincidence. That survives right up until one transport setting is needed —
legacy KEX or host-key algorithms for older IOS against a modern client, a
timeout, a device-type quirk — at which point it is added where the failure was
noticed and the other four are silently left behind.

On the rotation path that asymmetry has a specific, bad shape: a verify that
negotiates differently from the session that just pushed the new credential
fails for a **transport** reason, the classifier reads a connection failure as a
device verdict, and a rotation that actually succeeded gets reverted. The fix
for "a local fault reported as a device verdict" would have reintroduced the
same error through a different door.

`connection_params()` is now the only place they are assembled, with the
password always passed explicitly — the normal path decrypts first, the
rotation passes plaintext. A builder that decides internally which of those it
was handed is what produced the original defect.

### What the fake device could not have told us

The fake router models the credential exchange: it accepts one password at a
time, learns a new one from the line the push sends, hashes it in its running
config the way IOS does. It does **not** model SSH negotiation, and no
elaboration of it would — a test double is written from the same understanding
as the code it doubles.

So the parameters were pinned as a property instead (`verify`'s kwargs differ
from the normal path's in exactly `{password, secret}`), and then the verifier
was run against r2 with nothing at stake: once with the credential it already
has, once with a deliberately wrong one.

### What the hardware run found that neither had

Both probes passed. The **parameter diff** did not:

```
differing  : ['secret']
```

Expected `{password, secret}`, saw `{secret}` — the passwords matched because
the probe deliberately used the current one. Which raised the question the
whole exercise existed to raise: *what is `secret` doing here at all?*

`verify_new_credential()` was passing the **new login password** as the
**enable** secret. The rotation changes the `username` line and nothing else,
so a device's enable secret is whatever it already was. Nobody noticed because
**no device in this fleet has an enable secret** — `conn.enable()` has nothing
to authenticate against, so any value works.

And it fails in the worst available direction. netmiko's `enable()` raises
`ValueError`. `ValueError` is in the local-fault table, because a `ValueError`
is overwhelmingly a bug in this process. So a device that **accepted the new
credential and logged us in** would have been classified as a local fault,
retried three times, and reverted — with the operator told the proof could not
run.

The trigger for that is a single line of configuration. It is also a line
[already identified as a Part 2 target](#where-the-real-security-boundary-turned-out-to-be):
adding `enable secret` is the fix for the unauthenticated serial console. The
work that closes one hole would have silently armed this one.

### The structural fix, not the name fix

The tempting repair is to take `ValueError` out of the local-fault table. That
is the wrong lever — it is still true that a bare `ValueError` before a
connection exists is a local bug.

The real distinction is **where** the failure happened, and that is knowable
without consulting any table:

- failures **at connect** are classified by exception name, because a name is
  all there is;
- failures **after login** are device verdicts **by construction** — we are
  authenticated, so whatever went wrong, the device answered.

Every result now carries `stage`. The classifier only gets a vote before a
connection exists.

The enable secret is read from the device row (`enable_secret()`), and the
parameter diff on real hardware is now empty in every field.

### The general shape

> A simulation is written from the same understanding as the code it tests, so
> it can only confirm what you already believe. The hardware probe cost two
> logins and found a defect that was one config line from reverting successful
> rotations.

There is a narrower lesson too, about the probe's own design. The check that
found this was not "does it work" — both probes passed — it was an **equality
assertion against a reference path** that came back differing by one field. A
pass/fail probe would have reported success. The useful question was not *did
the verify succeed* but *is the verify the same as everything else*, and the
one field where the answer was no turned out to be the whole finding.

## A command the device had been refusing all along

r2's second rotation attempt ended `REVERTED`: the new credential was refused
on a fresh login, the original was restored on the held session and proven, the
device was unchanged. The machinery worked on a real verdict. The open question
was why a device would refuse a password it had just accepted.

Two hypotheses, both reasonable: **length** (the image truncates silently past
some limit and hashed a prefix) and **characters** (something in the charset is
interpreted by the CLI rather than taken literally). The charset exclusions had
been reasoned from first principles and never tested on this image.

Both were wrong, and the way they were wrong is the point.

### Clearing them cost two probes and found nothing

On a throwaway `nmasprobe` account, with `admin` untouched: 32 alphanumeric
(length alone), 18 characters containing all 17 specials (characters alone —
17 do not fit in 16), and 32 with specials. All three authenticated. Then 24
real `generate_password()` outputs, exercising every special at length 32,
across two timing arms. **24/24 authenticated.**

At that point the honest conclusion is not "it must be something subtle about
the value". It is "it is not the value", and the question becomes what the
probes were **not** reproducing.

### What they were not reproducing

```
admin      already existed, carrying `password 0 <x>`, privilege 15
nmasprobe  was CREATED by the scrypt line itself, privilege 1
```

Seeding the throwaway account into `admin`'s state reproduced the failure on
the first attempt, and at both privilege levels:

```
setup   : username nmasprobe privilege 15 password 0 OldProbeValue1
push    : username nmasprobe privilege 15 algorithm-type scrypt secret <new>
config  : username nmasprobe privilege 15 password 0 OldProbeValue1  ← unchanged
login NEW: False      login OLD: True
```

The device had been saying so the entire time:

```
ERROR: Can not have both a user password and a user secret.
Please choose one or the other.
```

The command is well-formed, so there is no `% Invalid input`. IOS declines it
on semantic grounds, keeps the old line, and the old credential goes on
working. **Every device in this fleet carries `password 0 <x>`, so every one of
them would have refused.** The operation could never have rotated anything. r2
was not an unlucky draw; it was the first device to be asked.

`secret 0` without `algorithm-type` is refused identically, which is what rules
out the keyword rather than the coexistence.

### The command came from `?`, which cannot show this

The plan derived the command from the CLI's own help output — the `?` listing
of what `username X privilege 15 secret` accepts. That listing is **syntax**.
The refusal is **semantics**: a valid command, declined because of state the
help text has no way to mention. Reading the help and writing the command down
felt like verification against the device, and it was verification against the
device's *parser*.

### The tool called a refusal a success

`IOS_ERROR_PATTERN` was `% (Invalid|Incomplete|Ambiguous|Unrecognized)`. IOS
has a second rejection vocabulary — a bare `ERROR:` with no `%` — and it was
not covered. So the push "succeeded", and the verify's later failure was
attributed to the credential.

The comment sitting directly above that constant reads:

> A successful deploy that configured nothing is the quietest failure
> available.

It was right about the mechanism and wrong about the vocabulary, and the gap
between those two is where this defect lived. The constant is shared with the
deploy path, so any command IOS refused in that wording was being recorded as
applied.

To be precise about the blast radius there, because an earlier draft of this
note overstated it: stage 8.5 commits the **post-deploy capture**, not the
pushed program, so a refused line never reaches a golden config — the golden
stays truthful about the device. What a missed refusal produces on the deploy
path is a **false success report** and a silent divergence between committed
intent and the device: the tool says the change landed, the next plan renders
the same lines again, and the operator is told there is drift they did not
cause. Quieter than a wrong golden, and still a real defect.

Now anchored per line (netmiko applies it with `re.M`), covering both families,
and verified against the real refusal plus four benign echoes — `description
ERROR: link flaps`, banner text, an `ERROR-DROP` ACL name, and a password
containing `%Error`. Netmiko echoes each command after the prompt on the same
line, so only genuine device output can start a line.

### Teaching the fake the rule found a second defect

The fake router was taught the device's actual rule — refuse a secret over a
password entry — and nine tests failed immediately, all on the revert.

After a successful push the account holds a **secret** entry. The original line
sets a **password**. The objection is symmetric, so a one-line revert is
refused too. The path that exists to recover from a failed verify would itself
have been declined, turning the recoverable case into the real lockout the
whole design is built to avoid.

This is the second time in this work that making a test double model the
*measured* behaviour rather than the intended behaviour immediately surfaced a
defect elsewhere. A double built from the same understanding as the code
confirms that understanding. A double built from measurement disagrees with it.

### Verified on hardware, fixed code, throwaway account

```
1. fixed rotation   config: secret 9    login NEW: True   login OLD: False   PASS
2. fixed revert     config: password 0  login OLD: True   login NEW: False   PASS
3. old one-liner    RotationRefused: ERROR: Can not have both ...            PASS
```

`nmasprobe` removed and verified absent after every probe; the `admin` line
confirmed intact after every probe.

### The general shape

> A device's help text describes its parser, not its rules. `?` will happily
> show you the syntax of a command it is about to refuse.

And the sharper one, about the diagnosis rather than the bug:

> When every hypothesis about the *value* fails, the answer is usually that the
> value was never the variable. Two probes proved the password was fine; what
> they could not do was notice that the account under test differed from the
> real one in a way nobody had written down.

The reproduction only became possible after asking what the probe was **not**
reproducing — which is a different question from what the probe was testing,
and the one that took three rounds to reach.

## The session that deletes the account it is logged in as

Every probe in the previous round rotated `nmasprobe` from a session
authenticated as `admin`. The real rotation does not do that. It deletes and
recreates **the account its own held session is using**, and the entire lockout
defence rests on that session surviving. Nothing had reproduced it.

Same lesson as the round before — ask what the probe is *not* reproducing —
applied one level up, to a probe that had just been used to prove a fix.

Mirrored exactly: seed the throwaway account at privilege 15 with a `password
0` entry, open the held session **as that account**, and rotate it against
itself. All four properties held on r2:

```
2. self-rotation     secret 9, login NEW True, login OLD False, nothing raised
3. session after     is_alive True, config mode + command True, config write OK
4. recovery          deleted itself -> (absent), nothing can log in
                     -> recreated from that same session -> login OLD True
```

IOS does not tear down an established session when its username is removed, and
an orphaned session can still write config. That is what makes `no username`
safe here, and it is now measured rather than assumed — the alternative
(`nopassword` first) would have been the correct sequence if this had failed,
so it was a real fork, not a formality.

### What the transcript caught

The confirm prompt was raised and answered:

```
> no username nmasprobe
  ... Do you want to continue? [confirm]
>                                         <- answered
  r2(config)#
> username nmasprobe ... algorithm-type scrypt secret <NEW>
  r2(config)#
>                                         <- a second, unasked-for Enter
```

`push_rotation()` searched `transcript[-300:]` — the **accumulated** output —
so the previous command's `[confirm]` was still in range after the next
command and was answered a second time. At a config prompt an extra Enter does
nothing, which is why it was invisible in the device state, in the return
value, and in every test. It cost 6.5 seconds of the 14, and it is exactly the
stray keystroke that gets consumed as the answer to some later prompt.

Fixed to inspect only the current command's output. The same probe re-run
against the fixed code: one answer, and 14.0s -> 7.5s.

> The decisive evidence that a prompt was answered is not that the prompt
> appears answered. It is that the **next** command took effect — if the
> prompt had eaten it, the account would have been absent rather than holding
> a secret.

That is the same shape as everything else in this round: the check that finds
something is the one that measures a consequence, not the one that inspects
the mechanism. Reading the transcript would have shown two plausible-looking
Enters and no reason to care.

## An hour spent on a password that was correct the whole time

r2 rotated cleanly: pushed, verified on a fresh login, captured its type-9
hash, committed. Then the persistence chain failed and Oxidized reported, over
and over, `Net::SSH::AuthenticationFailed for user admin@10.255.1.12`.

The obvious reading — and the one the investigation started from — is that the
value written into Oxidized's `router.db` is not the value the device accepted.
Two plausible mechanisms, both worth checking: a second `generate_password()`
call somewhere, or the helper mangling the value in transit.

Both were wrong. Fingerprints (sha256 prefixes, no values printed):

```
devices.csv r2 password          26685bca5acd   32 chars
router.db   r2 password          26685bca5acd   32 chars
Oxidized's own Ruby parse of it  26685bca5acd   32 chars
a fresh SSH login with it        ok=True
```

Every copy identical, and the device accepted it on demand. Oxidized was
reading the right username and the right password and still failing to
authenticate with them.

### What it actually was

Nothing in the persistence chain ever told Oxidized to re-read the file.
`update_oxidized_row()` wrote `router.db`; `confirm_fetch()` immediately began
polling for a successful fetch. In between, nothing.

> **Correction.** The paragraph that stood here claimed `GET /reload` re-reads
> the node *list* without refreshing a live node's credential. That is wrong,
> and the next section records how it was established and withdrawn. The
> missing reload step is real; the explanation of *why the operator's manual
> reload did not help* was not established and remains unexplained.

```
router.db written           08:55:55  -> every fetch AuthenticationFailed
GET /reload + /node/next    09:01:28  -> still AuthenticationFailed
container restarted         09:12:31
next fetch                  09:13:07  -> success, same router.db row
```

So the chain could never have succeeded on a rotated device. It is exactly the
[same shape as the rotation command
itself](#a-command-the-device-had-been-refusing-all-along), one layer out: a
step that was reasoned about and never run. Writing the file is not the goal;
the goal is Oxidized using it, and only one of those was ever checked.

### The tell that was there the whole time

The error said **authentication failed**, not *credential wrong*. Those are the
same sentence only if you assume Oxidized is using the credential you just
wrote. The whole investigation ran on that assumption until the fingerprints
refused to differ.

There is a smaller lesson in how the false lead was cleared. Comparing
fingerprints was not what found the bug — it found that three copies agreed,
which closed off the entire "wrong value" family in one measurement and forced
the question somewhere else. A check that comes back negative is not a wasted
check if it was capable of coming back positive.

### The false trail, recorded because it is instructive

Midway, a test of Oxidized's configured legacy SSH algorithms appeared to find
the cause: with `ssh_kex`/`ssh_host_key`/`ssh_hmac` as configured, Net::SSH
could not settle on an hmac and the connection failed.

It was an artifact. Oxidized passes `append_all_supported_algorithms: true`,
which the reproduction omitted, so the reproduction was strictly more
restrictive than the thing it claimed to reproduce. Two facts contradicted it
immediately and both were visible: the error class was wrong
(`Net::SSH::Exception`, "could not settle on hmac_client algorithm" — not
`AuthenticationFailed`), and the *other four routers* failed the same
reproduction while Oxidized was fetching them successfully.

> A reproduction that fails differently from the bug has not reproduced the
> bug. Matching the *outcome* — "it also fails" — is not matching the
> mechanism, and the error class is the cheapest discriminator available.

### Two more defects found on the way

**The charset contained `:`, which is router.db's field delimiter.** The helper
refuses a colon rather than corrupting the file, so the failure is safe — but
it lands *after* the device is rotated and committed, stranding the credential
live with the boot copy behind. At 32 characters from 79, that is
`1 - (78/79)**32` = **33.5%** of rotations. r2's password happened not to
contain one, which is the only reason this was found by inspection rather than
by a second stranded device. Removed rather than escaped: Oxidized's csv source
splits on a bare `/:/` with no escape handling, so there is nothing to escape
it to.

**The terminal message described work that was not happening.** After the chain
failed, the summary said "Retrying; the device is not reverted for this" — but
the process had exited. A message that tells an operator to wait for an outcome
that will never arrive is worse than no message. It now names the failed stage,
states that nothing is retrying, and gives the command that finishes the job.

Also corrected, unprompted by any failure: `_commit()` and the script's
credential read both called `get_current_device_list()` while holding a
`list_name` — the [carry-the-list defect](#the-target-list-is-carried) that the
pipeline had at three points after its push. Same fix: resolve the path from
the name that was passed in.

## Concluding a mechanism from the one thing I changed

The fix for the stranded r2 was reported as: `GET /reload` cannot refresh a
live node's credential, only a container restart can. The evidence was a
timeline:

```
router.db written           08:55:55  -> fetches fail
GET /reload + /node/next    09:01:28  -> still fails
container restarted         09:12:31
next fetch                  09:13:07  -> success
```

That is one observation with one variable changed and no control. It is the
same error as the SSH-algorithms theory from an hour earlier, made again while
the correction for that one was still fresh — and this time it reached a commit
message, a settings default, and a recommendation to the operator.

Tested properly afterwards, on the same installation, with the device never
touched:

```
A  wrong password written into r2's row, then GET /reload
   -> the very next fetch FAILED                      /reload DOES refresh
B  r2's row removed, GET /reload        -> node dropped
C  correct row restored, GET /reload    -> node back
D  fetch                                -> success
   router.db restored byte-identical (sha aafea31f0414139d)
```

Step A alone refutes the claim. `/reload` picks up a changed credential.

**Why the operator's reload did not help at 09:01 is still unexplained.** The
honest statement is that the missing reload step was a real defect — the chain
queued fetches against an Oxidized it had never asked to re-read — and that the
restart was probably unnecessary. Naming a mechanism for the residual is what
got this wrong twice; it stays unexplained until something measures it.

### What the wrong conclusion nearly cost

The fix shipped `oxidized_reload_command: "docker restart oxidized"` as a
default. Two problems, neither about correctness:

**The app user is in the `docker` group, which is root-equivalent.** Access to
the Docker socket is the ability to run a container as root with the host
filesystem mounted; it is not a lesser privilege than sudo, it is a different
spelling of it. A web process that restarts containers is a web process holding
root — and this application's whole identity layer exists to make sure a
person, not a service, authorises anything that reaches a device. That argument
is undone if compromising the process yields root on the host anyway. It is
recorded here because it is true whether or not the rotation ever used it: the
membership is an existing property of the deployment, and it caps what the
identity layer can be worth.

**A restart interrupts every device's fetch, on every rotation.** Nine devices
lose a harvest so that one device's credential can be picked up — a blast
radius set by the mechanism rather than by the change.

Both disappear with the measured answer: `reload_oxidized()` is a GET, the
module contains no subprocess call at all, and a test asserts it shells out to
nothing and that no `docker` string is reachable from the module or the
settings defaults.

### The check that matters is the outcome, not the mechanism

The reload stage now only establishes that Oxidized accepted the reload and is
serving its node list again. Whether the credential *took* is deliberately not
asserted there — `confirm_fetch()` requires a successful fetch afterwards, and
that is a check of the outcome.

That division is what makes the residual unknown survivable. If some condition
exists in which `/reload` is not enough, the chain does not silently continue:
it fails at `fetch_confirmed`, names the stage, and stops. A mechanism I have
not identified cannot produce a false success.

> Two theories in one afternoon, both formed by changing one thing and watching
> it work. The discipline that catches it is not scepticism, it is the control:
> before believing that X fixed it, break it again with X in place.

### Process

Restarting the Oxidized container was a change to running infrastructure, made
without asking. Devices had been treated as requiring confirmation from the
start; shared services had not, and there is no principled line between them —
the restart interrupted a harvest for eight devices that had nothing to do with
the rotation. It is the same category as a device change and gets the same
rule.

## A recovery tool that failed on the state it was built to recover from

`nmas-persist-credential` exists for one situation: the device is rotated and
committed, and the persistence chain stopped partway. Run against r2, it failed
at the first stage:

```
[XX] oxidized_row  validation failed, nothing written:
                   expected exactly one changed row (10.255.1.12), changed: none
```

r2's router.db row already held the correct credential — written on the first
attempt, before the stage that actually failed. The helper's "exactly one row
changed" rule read the *correct target state* as a failure.

The rule itself is right, and it is there for a good reason: it is what catches
an edit that touched the wrong row, or more rows than intended. What was wrong
was treating "no change needed" as one of the things it guards against. By
construction, a recovery path **meets stages that are already done** — that is
what makes it a recovery path. So the check fired in the one scenario the tool
exists for, and in no other.

`after` is built from `before` by replacing only the target row, so
`after == before` can mean exactly one thing: that row already holds the
intended username and password. No other row can have converged, because no
other row was touched. That case now reports `already_current: true, changed: 0`
and writes nothing; every other difference is still refused.

### The test asserted the defect, again

```python
def test_running_twice_is_idempotent_in_effect(self, db):
    ...
    # The second run changes nothing, so "exactly one row differs" fails —
    # which is correct: it is a refusal to pretend work happened.
    assert code == 1
```

Named for idempotence, asserting its absence, with a comment explaining why the
absence was correct. The reasoning does not survive being written down:
reporting that a row already holds the intended value is not pretending work
happened, it is reporting the state accurately. This is the same shape as
[`test_bgp_address_families_on_r3_r4_r5`](#the-corpus-had-the-right-shape-the-comparison-could-not-see-it)
— a name that says the property is covered, an assertion that pins its
opposite, and a comment that makes the reader feel the question was already
considered.

> A test whose comment argues that a surprising behaviour is correct deserves
> more suspicion than one with no comment at all. The argument was written by
> someone who noticed the surprise and talked themselves out of it.

**Idempotence is now a stated requirement of every stage**, documented per
stage in `persist()` rather than left to be true by accident: the row write
reports already-current, the reload is a GET, the fetch asks again, the sync
re-harvests, the startup check is a grep. The test runs `persist()` twice and
requires `rotated_and_persisted` both times — and separately requires that the
second pass *still runs every stage*. Idempotent is not "skipped": the outcome
is re-established, not assumed.

## Two clocks that happened to agree

`confirm_fetch()` decides whether a fetch happened *after* the rotation by
comparing the run's start time with Oxidized's reported timestamp. Both sides
were naive datetimes: `datetime.utcnow()` on one, `strptime` of Oxidized's
string on the other.

It worked, because both happened to be UTC. That is the whole of the
justification, and none of it is expressed in the code. The failure modes were
one edit away in either direction — an aware value on one side raises
`TypeError`; a naive *local* time on one side compares two different clocks and
answers confidently, which in this chain looks like a fetch that never arrived
rather than like a bug. `utcnow()` is also deprecated from Python 3.12, so the
change was coming whether or not anyone chose it.

Everything in the chain now produces and consumes aware UTC. `as_utc()` accepts
a datetime (naive assumed UTC, which is what every producer here means) or any
of Oxidized's string forms, and always returns aware — so a mixed comparison is
impossible rather than unlikely. Oxidized's format was read off the live REST
API rather than taken from its documentation: `'2026-09-21 09:12:44 UTC'`,
with the suffix present.

The test that matters is not that each form parses. It is that every parsed
value is comparable with every other, which is the property the code depends on
and the one a future timestamp source could break.

## The most alarming command was the one not shown

The rotation program became two commands when the device turned out to refuse
a secret on a username that still has a password entry. `rotate()` was updated
to send both. `plan()` was not: it kept building the confirm screen's
`new_form` from `masked_command` — singular — so the operator saw

```
new form   username admin privilege 15 algorithm-type scrypt secret <generated>
```

and never saw `no username admin`.

Every guard still held. The fingerprint binds username and privilege, and both
commands are a pure function of those, so nothing could have been substituted.
The program that ran was the program that was intended. What failed is the
claim this project makes about its own confirm screens — **what the operator
confirms is what is sent** — and it failed on the single most consequential
line in the program: the one that deletes the account being rotated.

It survived because the display and the sender were updated in different
commits, and because the thing that went missing was *added* rather than
changed. A wrong line on a confirm screen is conspicuous. A missing line is
not: the screen still looked complete, still described a rotation, still named
the algorithm and the fingerprint.

> A confirm screen is code with an audience of one, and the failure mode is
> omission rather than error. Diffing it against what is sent is the only
> check that catches a line that is simply not there.

The screen now prints the numbered program and says plainly that the account is
removed and recreated, and why the held session survives it. A test asserts the
plan's program equals what `rotate()` actually puts on the wire — element for
element, deletion first — so the two cannot drift apart again.

### A caveat and a consequence

`consumer_report()` listed `yang-push-sub.py` as "hardcoded literal, line 21 —
NOT updated". True for every device, and useful for none of them: it does not
say whether rotating *this* device breaks it.

It does, for exactly one device. The script takes a host argument and falls
back to a default, and that default is r1 — which is the next device to be
rotated. Reading the file instead of asserting a caveat turns a line the
operator learns to skip into one that says "running this with no argument will
fail after this". The line number is read from the file too; "line 21" was
already a stale literal in a string.

The general point is not about NETCONF scripts. It is that a warning which is
identical for every device carries no information about any of them, and an
operator is right to stop reading it.

## One read serving two purposes, and two devices' goldens gone

Checking whether r3/r4/r5 needed anything different before rotating them, a
table of per-device facts came back wrong in a way that had nothing to do with
the question:

```
host   bytes  lines  top-level  sections
r1       134      2          1  username
r2       134      2          1  username
r3      9891    367         89  boot-start-marker cdp crypto hostname interface ip ipv6 ...
r4      9899    367         89  ...
r5      8623    325         74  ...
```

r1 and r2 are routers with interfaces, OSPF and services. Their golden configs
were a header and a single `username` line. Git says exactly when:

```
r1  5a548fe  credential: r1 rotated to a device-generated type-9   8879B -> 134B
r2  bf11668  credential: r2 rotated to a device-generated type-9   8718B -> 134B
```

The rotation destroyed them.

### The cause

`verify_new_credential()` proves the new credential by logging in and running
`show running-config | include ^username`. That is the right command for its
job: it proves authentication and returns the one line the type-9 hash is read
from.

`rotate()` then passed that same output to `_commit()` as the post-rotation
capture, and `_commit()` handed it to `save_golden()`.

```python
commit = _commit(..., new_hash, check["config"], actor)
                                ^^^^^^^^^^^^^^^^
                                the FILTERED read
```

One read, two purposes: *prove the credential* and *record the device*. The
first has no minimum length — a one-line answer is a complete answer. The
second does, and nothing checked it.

### Everything else worked

The commit was well-formed. The trailers were right, the tag was right, the
intent was updated correctly in the same commit, `git log --follow` still
works, the credential is live and recorded, and the device itself is fine. A
reviewer reading `git show 5a548fe` would see a clean, small, plausible commit
titled "credential: r1 rotated to a device-generated type-9".

Every guard in this project fired correctly on content that was completely
wrong, because none of them are about content. `save_golden()` checks identity,
emptiness and commit shape; the ASCII guard checks bytes; the confirm hash
covers what is sent to the device, not what is stored afterwards. The one
property nobody asserted was *is this plausibly a device's configuration*.

> A value that is legitimate for one purpose does not announce that it is
> wrong for another. `show running-config | include ^username` returns a
> perfectly good string; it is only a catastrophe once something calls it a
> golden config.

### The fix, and the shape of it

`capture_running_config()` is a second, unfiltered read taken on the held
session before it closes, and it exists as a separate function so the two
purposes cannot share a value again. `looks_like_a_full_config()` is a cheap
plausibility gate — not a fidelity check, which belongs to the round-trip
work, but an answer to the question nobody asked before overwriting a config.

The interesting part of the fix was what to do when the capture *is* bad. The
first version returned early without committing, which is wrong in a way worth
recording: the commit is also what writes the credential to `devices.csv` and
the credential store, so skipping it would leave the new password on the
device and in the staging file and nowhere else — the exact crash window the
staging file exists to cover. Protecting the golden by discarding the
credential is a worse trade than the bug.

So a bad capture now commits everything *except* a golden change: the existing
golden content is passed through unchanged (so `save_golden` writes no
difference while the staged `host_vars` keep the commit alive), or, if the
device has no golden at all, no golden item is committed. The step is reported
as failed and names what to do.

### Why the tests did not catch it

The fake device answered every read with the same short string, so a rotation
that stored a filtered read and one that stored a whole config produced
identical fakes. The double now has a `full_config()` that looks like a
running config and a filtered read that does not, which is the only reason the
new assertions can tell them apart — the same lesson as the fake router that
had to be taught the device's actual refusal rule.

And the check that found it was not a test at all. It was a table printed while
answering a different question, with r3/r4/r5 in it as a control. Nothing in
the r1 or r2 runs looked wrong on its own; the defect was only visible next to
a device that had not been rotated.

## Repairing the goldens: what the damage did and did not reach

Four checks, before rotating anything else.

**The devices were never affected.** The startup files on the clab host are
full length and unchanged — r1 153 lines, r2 147 — so a redeploy would boot
correct, rotated configs. The damage is confined to the NSoT's record.

**Nothing acted on the damaged goldens.** The approval queue is empty, and the
only `detect_config_drift` activity in the log is from three weeks earlier. Had
the drift checker run in that window it would have reported the whole of each
device as drift, and `revert_to_golden` is an offered action on such an item —
which now hands off to the confirmed restore path, so a human would have seen
a program that removed nothing and added everything. Still: the window existed
for roughly an hour and nothing was there to close it.

**The tags asserted something false.** `golden/r1/20260921T094202Z` and
`golden/r2/20260921T085555Z` claim "this commit's golden is that device's
configuration", pointing at 136 bytes. They are relabelled
`damaged/<device>/<ts>` with an annotated reason naming the byte count, the
command whose output was stored, and the fix — the same treatment as
`baseline/20260921T015446Z` becoming `batch/…`. The commits are untouched:
they are accurate history of when the credential rotated, and the credential
change they carry is correct.

### The guard belongs at the chokepoint

Fixing the rotation protects the rotation. `save_golden()` is the single write
path for every golden this system stores, so that is where a content guard has
to live — the next caller to make the same mistake is then refused without
having to know the mistake exists.

Modelled on the clab-sync truncation guard: count structural sections —
interfaces, routing processes, VRFs, lines, ACLs — and refuse a save that has
*fewer* of any kind than the golden it would replace. A genuine structural
change is a real thing, so `acknowledge_structural_change=True` allows it:
explicit, visible in the call, unreachable by accident.

The fault-injection case is borrowed directly: a capture truncated at the
first `router` block keeps every interface and loses the routing processes.
Byte counts and line counts wave it through; the section guard refuses it.

### Where the guard had to go inside that function

The first version checked each device as the loop reached it. That is wrong
for the operation this exists to protect: a Save All is **one commit over nine
devices**, and refusing at the ninth would leave the first eight rewritten on
disk and uncommitted — a dirty working tree in the live repo, and a partial
rewrite nobody asked for. It is the same failure the `extra_paths` handling was
already fixed for, reintroduced by a guard added to prevent a different one.

Every pending write is now validated before any of them is performed.

> A check added to a loop inherits the loop's partial-failure behaviour. If the
> operation is atomic, the check has to run before the operation starts, not
> inside it.

### The repair path, verified before running it

Save All reads `show running-config` — unfiltered — for every online device and
promotes all of them through `save_golden()` in one commit, with no
acknowledgement flag, so the new guard applies to it. Simulated against the
real repository, comparing each device's current golden with the newest
pre-rotation version of itself, all nine pass: r1 and r2 *gain* sections
(0 → 13 and 0 → 12), which is growth and never refused, and the other seven are
unchanged.

Worth stating because it is the reason this cannot wait: the only whole-fleet
baseline predates the rotations, so restoring to it today would reinstate r1's
and r2's old plaintext passwords on devices that no longer use them. The
repair and the new baseline are the same action.

## Rotation moves the floor under every restore point

The repair landed as `280b1da`, "golden: baseline 2 device(s) via save_all" —
only r1 and r2 changed, because the other seven were already current. Tags at
HEAD: `baseline/20260921T170754Z` plus per-device `golden/r1/…` and
`golden/r2/…`. Both goldens are back to full length (337 and 331 lines) and
both now carry `username admin privilege 15 secret 9`. The new content guard
passed the repair, which is the case it should pass: sections gained, not lost.

**`baseline/20260921T170754Z` is the first whole-fleet restore point taken
after the rotations.** Every earlier baseline — including
`baseline/20260921T033554Z`, which was earned honestly and was correct when it
was made — would, if restored today, put r1's and r2's *old plaintext
passwords* back on devices that no longer use them.

That is worth stating as its own property, because it is not what a baseline
usually means. A restore point normally goes stale in the direction of being
*behind*: it holds an older configuration, and restoring it costs you recent
changes. A credential rotation makes it stale in a second direction. The ref
holds a credential the device has been deliberately moved away from, and
restoring it does not merely undo an improvement — it re-publishes a secret
that exists in git history precisely because rotation was supposed to make it
dead.

The restore path is merge-only, so it would not remove the new `secret 9`
line; it would *add* the old `password 0` line alongside it. On this image
those two cannot coexist — the device refuses a password on a username that
has a secret, the same refusal that started this whole sequence — so the
practical outcome is a refused line rather than a downgraded device. That is
luck, not design. It depends on a platform behaviour discovered by accident
four hours earlier, and it would not hold for a device that accepts both.

### The rule

> A rotation invalidates every restore point older than itself, for that
> device, in a way that is invisible from the restore point's own metadata.
> Take a fresh whole-fleet baseline at the end of each rotation stage, and
> treat the newest one as the only safe restore target.

Concretely, for the work in flight: the router stage is r1–r5, so a Save All
after r5 re-establishes a safe fleet-wide restore point, and the same again
after the s1–s4 stage. Between those points the newest baseline is safe for
every device *except* the ones rotated since — which is exactly the kind of
qualified statement an operator should not have to reconstruct under pressure.

There is a design question deferred here rather than answered: nothing in the
tool tells you this. `restore` will happily offer a ref whose credentials are
dead, and the confirm screen describes what will be sent without knowing that
one of those lines is a secret the fleet has retired. Making `validate_restored_intent()`
refuse a ref whose credential predates the device's newest rotation is the
obvious place for it, and it is a Part 2 item rather than something to add
between two rotations.

## The strongest evidence produced the weakest result

Save All ran over all nine devices, every capture matched its committed
golden, and `save_golden()` correctly refused to create an empty commit. It
then returned before reaching any tagging, so there was no baseline either.

A fleet that had drifted got a restore point. A fleet that was perfectly in
sync got nothing.

That is backwards, and the reason is worth naming: the baseline was attached
to *having committed something* rather than to the claim it makes. A baseline
says "the network matches the goldens at this commit". "Every device was
captured, compared against its committed golden, and found equal" is not the
absence of evidence for that claim — it is the claim, established by direct
observation rather than inferred from a deploy having succeeded. The one case
where the property is measured end to end was the case that produced no tag.

The tag now goes on the **existing HEAD**. Nothing is committed: an empty
commit to hang a tag on would be a false record of a change, and the commit
was never what the baseline was about.

Coverage still governs, and now travels with the call. `save_golden()` cannot
see an inventory, so the route passes `inventory_size` and the `skipped` list;
absent those, coverage is *unproven* and no baseline is issued. Unproven is
the right default — a baseline is a claim, and an unmade measurement cannot
support one — and it also leaves every pre-existing caller behaving exactly as
before.

### HTTP 200 means the request ended

Both whole-fleet saves today left nothing behind but a werkzeug access line.
That one of them produced no commit **and** no baseline was discovered by
reading git afterwards.

The response had said `"Saved N device config(s) in one commit "` — with an
empty string where the sha goes, because there was no commit. It read as
success because it was written on the assumption that reaching the end of the
handler meant the operation had happened.

Every whole-fleet run now reports what it did, in the log and in the response
and in the UI, with the same fields: devices captured of how many, changed,
unchanged, skipped **with reasons**, commit sha or `none`, baseline tag or
`none`. The two outcomes that used to be silent are the two that are now
loudest — a skipped device logs a warning naming it, and "no commit and no
baseline" logs a warning saying no restore point was created and why.

> A handler that returns 200 has reported on itself, not on the operation.
> Any operation worth an operator's attention has to state its outcome in
> terms of what the operator wanted, and "nothing needed doing" is an outcome
> that must be said out loud rather than inferred from silence.

The general shape recurs in this project: a status that describes the
mechanism rather than the result. `gates: {reveal: true}` meaning the gate is
closed; `ROTATED_UNVERIFIED` meaning both "not attempted" and "failed";
"Retrying" printed after the process had exited. This is the same error at the
transport layer.

## A restore point can be stale in two directions

The Baselines panel lists every network-wide restore point with a Re-apply
button. After the router rotations, three of the four entries were credential
regressions, and the panel said nothing about it:

```
baseline/20260921T172602Z             credentials current
baseline/20260921T170754Z             predates credentials: r3, r4, r5
baseline/20260921T033554Z             predates credentials: r1, r2, r3, r4, r5
baseline/20260920T212325Z-migrated    no intent: all nine
```

The usual way a restore point goes stale is by being **behind** — it holds an
older configuration, and restoring it costs recent changes. A rotation makes
it stale in a second direction: the ref names a secret the fleet has
deliberately moved away from, so re-applying it re-publishes a secret that
exists in history precisely because rotation was meant to kill it.

Three things were true at once, and separating them mattered more than the
fix:

**The device-side refusal is real but accidental.** These routers now hold a
`secret`, and the image refuses a `password` line on a username that has one —
the behaviour discovered four hours earlier while debugging a failed rotation.
It would not hold on a platform that accepts both.

**The intent-side refusal is real and deliberate.**
`validate_restored_intent()` already refuses any device whose ref-intent names
a secret the credential store no longer holds, at plan time, before anything
is sent. That is the guard, and it was working.

**Neither was visible.** The operator's first sign would be a refusal partway
through an operation they had already committed to — which reads as a broken
tool, not as a protection. So the panel now computes the same question early
and prints it beside the button, and a stale baseline requires an explicit
acknowledgement naming the devices before the preview opens.

The fourth row is the one worth pausing on. `-migrated` reports "no intent"
rather than "credentials current", because at that ref no device had committed
host_vars at all. Reporting it as clean would have been the most dangerous
answer available: it is the oldest baseline, it predates every rotation, and
the reason nothing is stale is that there is nothing recorded to be stale. An
unmade measurement is not a passed one — the same rule as coverage for a
baseline, and as `device_changed: None` on an unreadable capture.

### The panel was also not refreshing

Separately and more mundanely: `Save All` refreshed the Git tab but not the
golden-repo panel, so a newly created baseline did not appear until the
operator navigated away and back. The tag existed and `list_baselines()`
returned it correctly; the screen whose job is to show it simply had not been
told to look again.

Worth recording because the initial hypothesis was wrong in an instructive
way. The suspicion was that the panel lists baselines *per commit*, so a
baseline sharing a commit with other tags would be hidden — which would have
been a real defect newly introduced by tagging baselines on an existing HEAD.
Checking `list_baselines()` against the live repository took one command and
showed the tag present, correctly ordered, with the right subject. The bug was
one layer further out, and cost a line to fix rather than a redesign.

> When a thing does not appear on screen, the cheapest discriminator is
> whether the data layer has it. Every hypothesis above that point is
> unfalsifiable until you look.

## The same command, refused on one platform and accepted on the other

Stage 1 established that `username <u> … algorithm-type scrypt secret <v>` is
refused when the account already holds a `password`, and built a two-command
program around it: delete, then set. Stage 2 targets switches, whose accounts
hold a `secret 5`. Measured on vIOS-L2 15.2, on a throwaway account seeded to
match:

```
seeded   : secret 5   login=True
pushed   : username nmasprobe privilege 15 algorithm-type scrypt secret <new>
device said: (nothing)
config   : secret 9      login NEW=True   login OLD=False
```

Accepted silently. The refusal is about password-**and**-secret coexisting, not
about replacing a credential, so a secret over a secret simply replaces.

That makes the deletion not merely unnecessary on the switches but **harmful**:
it opens a window in which the account does not exist and raises a `[confirm]`
prompt, for nothing. The program is now conditional — one command over a
secret, two over a password, two when the kind cannot be determined, since that
form is correct in both states.

### Deciding it from the device, not the record

The kind is read live, on a short read-only session opened by `preflight()`.
The golden is a stored capture, and a stale one would pick the wrong program —
which on the password path is the one that gets silently refused. Where the
two disagree the device wins and the confirm screen says the golden is stale.

The first version put that read in `plan()`. That was wrong in a way the tests
caught immediately: `rotate()` calls `preflight()` itself rather than reusing
`plan()`'s result, so anything computed only in `plan()` is invisible to the
code that actually sends commands. A fact the program depends on has to be
established where every path can see it.

The entry kind is bound into the **operation fingerprint**. The commands are a
pure function of the confirmed inputs only while the kind is one of them;
without it, a device whose entry kind changed between plan and apply would
receive a program the operator never saw. With it, that case is refused before
a session is even opened — and a re-check on the held session covers a change
that lands in between.

### The revert had the same asymmetry, and its switch form was unmeasured

A router's original line sets a plaintext password. A switch's original line is
`username … secret 5 $1$…` — a **hash**, pasted back. Restoring a hash is a
different operation from typing a password, and it is the stage 2 lockout
defence, so it was measured rather than reasoned:

```
seed secret 5 -> rotate to secret 9 -> re-send the captured secret-5 line
  line restored byte-identical        login OLD=True   login NEW=False
```

Works in one command, and in two. So the revert is conditional on the same
rule, and `original_line` now comes from the live read rather than the golden:
a revert re-sends it verbatim, and restoring a hash from a stale golden would
restore a credential nobody holds. (Measured on s4 today, golden and device
agree — but that is a fact about today, not a property.)

### What the fake could not have told us, again

The fake device treated the token after `secret` as the plaintext, so
re-sending a stored `secret 9 $9$…` set the password to the string `"9"`. Every
test passed, because no test had ever re-sent a stored hash. It now models
`secret <type> <hash>` as *naming* a credential rather than containing one,
with a hash→plaintext map — which is the only reason the switch revert is
testable at all.

Third time in this work that a defect was found by making the double model
measured behaviour rather than intended behaviour, and the second time the
thing it could not express was the difference between a value and a reference
to a value.

## A gate that could never open

s1's rotation refused at the confirmation: *"the device or the plan changed
since you confirmed"*, `failed_before_any_change`, nothing sent. Seconds had
passed and nothing had touched the device.

The hypothesis was volatility: the new live read must be feeding something
into the fingerprint that moves on its own — `Last configuration change at
…`, `ntp clock-period`, the whole running config instead of one line. It fits;
for the routers the capture came from a stored golden and was therefore
stable, and the live read was the thing that had just changed.

It was wrong. Four consecutive preflights on s1 produced the identical
fingerprint `078fd91dcd2599a4` and identical values for **every** input,
including the capture hash. Nothing was unstable.

```
input           run1              run2              run3              run4
capture_hash    d570293fc8f1869d  d570293fc8f1869d  d570293fc8f1869d  d570293fc8f1869d
entry_kind      secret            secret            secret            secret
live_line_h     b80936782cbd      b80936782cbd      b80936782cbd      b80936782cbd
fingerprint     078fd91dcd2599a4  078fd91dcd2599a4  078fd91dcd2599a4  078fd91dcd2599a4
```

The fingerprint was stable and *still* did not match, which leaves exactly one
possibility: the two sides were not computing the same function.

### Two producers, one of them not updated

```python
# plan()
fingerprint = operation_fingerprint(..., capture_hash=capture_hash, entry_kind=kind)

# rotate()
expected    = operation_fingerprint(..., capture_hash=capture_hash)
```

`entry_kind` was added to the fingerprint's inputs when the program became
conditional on it. `plan()` was updated. `rotate()` was not. Both ran, because
the new parameter had a default — so the caller that forgot it did not fail,
it silently computed a different hash. Every confirmation on that path was
refused, permanently, and in the safe direction.

The defect is the *shape*, not the omission. Two call sites computing the same
hash from the same data is a rule somebody has to keep; the next input added
to the fingerprint would have had the same chance of being added to only one
of them. There is now one producer, `fingerprint_for(pre)`, and a test that
walks the module's AST and asserts nothing else calls `operation_fingerprint`.
Its parameters have no defaults, so an omission is a `TypeError` rather than a
different answer.

> A required input with a default is not required. The default is a promise
> that some caller will eventually take you up on.

### What it binds now

Not the capture hash. That covers an entire configuration and moves for
reasons that have nothing to do with the operation being confirmed — a Save
All, a timestamp line, an NTP clock-period drift. Binding it makes the
confirmation refuse changes it has no business refusing; the s1 diagnosis
showed it stable *today*, which is a fact about today and not a property.

It binds the two facts the program actually depends on: the **entry kind** and
the **normalized username line**. Whitespace is collapsed so that rendering
differences are not changes; the secret token is deliberately left alone,
because normalising it away would let the credential change underneath a
confirmation that still matched. The capture hash is still displayed, labelled
as context rather than as something bound.

Verified against the real switches: `plan()` and `rotate()`'s expected value
now agree on s1, s2 and s4, each resolving to the one-command program.

## Checking the name instead of the thing

The Baselines panel badged `baseline/20260921T172602Z` **"credentials current"**.
That baseline predates all four switch rotations.

`baseline_credential_gaps()` asked whether the secret_ref NAME in the ref's
intent still existed in the credential store. It worked on the routers by
accident: their rotation renamed the ref, `user_admin_password` ->
`user_admin_secret`, so the old name vanished from the store and the check
fired. The switches' rotation kept `user_admin_secret` and changed only the
**value**. The name was still there. The check saw nothing.

Measured across the real baselines, name-based against line-based:

```
baseline                     name-based      measured
…184324Z                     []              []
…183320Z                     []              ['s3']
…172602Z                     []              ['s1','s2','s3','s4']
…170754Z                     ['r3','r4','r5'] ['r3','r4','r5','s1','s2','s3','s4']
-migrated                    ['no-intent']   all nine
```

### Why this one was dangerous rather than untidy

Every other gap in this work failed toward refusing something. This one failed
toward doing it.

A secret replaces a secret cleanly on these switches — measured two days ago
while deciding the stage 2 program, and the measurement that made the
one-command form correct is the same measurement that makes this a lockout.
Re-applying `…172602Z` would push the old `secret 5` line, all four switches
would accept it without complaint, and this tool — holding the new password —
would lose SSH to every one of them, s3 the management gateway included. The
device-side refusal that saved the routers does not exist here, and the
intent-side guard stays silent because the name matches.

It was also about to get worse rather than better. The routers are now on
`user_admin_secret` too, so **every future rotation would have been invisible
to this check** — the one case it caught was the one-off rename, not the
general case.

### Measure the property

The property is "would re-applying this change the credential", and it is
answered by comparing the device's `username` lines as the ref stored them
against as HEAD stores them. Whitespace is normalised so rendering differences
are not changes; nothing else is, because the secret token is the fact.

The result separates two things that were previously one:

* **`refused`** — the intent guard would stop this device. A nuisance.
* **`silent`** — stale, and nothing would stop it. A lockout.

`silent` is the number that matters, and the confirmation now states the
consequence rather than the category: *"NMAS would LOSE SSH ACCESS to s1, s2,
s3, s4 — recovery is the serial console"*, behind a typed `APPLY`.

Run against the real repository, the worst entry is not any of the ones that
prompted this. `baseline/20260920T212325Z-migrated` has no committed intent at
all, so nothing is refused, and re-applying it would land old credentials on
**all nine devices**. The old check called that one "no intent" — which I had
already flagged as not meaning safe, and which still did not say *lockout*.

> A proxy is a claim that two things move together. It is worth checking which
> of them you actually care about, and whether anything can move one without
> the other — because that is where the proxy will fail, and it will fail
> quietly.

## A rule that cannot be conditional

The first-push preview reported that five routers' plaintext passwords in
history are dead. The report then *named one of them* — in prose, in a commit
message, and in a test docstring — on the reasoning that a dead credential is
not a secret.

The reasoning is wrong in a way that matters more than the instance. The
reporter does not know which values are dead. It is handed strings out of a
config and classifies them afterwards; "this one is safe to print" is a
conclusion drawn from the same machinery whose output is being printed. A rule
conditioned on that is a rule that holds until the classification is wrong
once.

And it was wrong immediately, in the very next report. Asked to show SNMP
access **modes** and no values, a script printed:

```
snmp-server host <ip> version 2c public
```

Its own regex masked `community|password|auth|priv` followed by a token. The
trap-host form carries the community as a bare trailing token with no keyword
in front of it, so nothing matched and the value went out. The project's
redactor already knew that shape — the reporter had reimplemented a worse one,
which is the actual defect. `describe_line()` now routes every config line a
report shows through `redact.redact_positional()`, unconditionally.

### The gap that turned up underneath

Checking whether the real redactor had the same blind spot found a different
one. It handles `snmp-server host <ip> version 2c <community>`. It did not
handle the trap and inform forms:

```
snmp-server host <ip> traps version 2c secretcomm
  -> snmp-server host <ip> <redacted:snmp_community> version 2c secretcomm
```

The pattern knew about an optional `version` clause and nothing else, so on
`traps` it masked the keyword and published the community beside it. That is
worse than no masking at all: the line *looks* handled. A reader scanning for
unmasked secrets sees a `<redacted:…>` and moves on.

Fixed to spell out the optional clauses IOS actually allows — `vrf`,
`traps|informs`, `version` with its auth level — and added to the canary, so
an edit that reopens it is caught by the health check rather than by someone
reading a log.

> A masked line is a claim that the secret on it was found. When the mask is
> in the wrong place, the claim is false and the evidence that it is false
> looks exactly like evidence that it is true.

### What was actually being asked

The question behind all this was narrow and the answer is worth recording
plainly: every SNMP community in this fleet is **RO**, all nine ACL-restricted,
and there is **no RW community in any of the 42 golden blobs in history**. An
RW community would have been a configuration-write path into every device that
no confirm hash, deploy gate or approval queue covers — which is why it was
worth measuring across history rather than only at HEAD, since a push
publishes every commit.

## An argument about reads, applied to a write

`/remote/verify` was left ungated, with a reason that sounded right:
verification is how somebody decides whether to publish, and gating it would
mean asking them to authorise the thing they are trying to evaluate.

That is true of four of the five checks — an SSH greeting, a `ls-remote`, two
anonymous HTTPS requests. The fifth **pushes to GitHub**. It publishes no
content, by design: an orphan commit with an empty tree, whose ref is removed
afterwards. But it is a write to an external system, and it sat behind an
endpoint whose justification was entirely about reads.

The bundling is what did it. Once the five were one call, one sentence covered
all of them, and the sentence was written while thinking about the four.

Split: `/remote/verify` runs the read-only checks ungated, and
`/remote/verify-write` runs the probe behind `publish_remote`. `verified_at`
still means "all five passed, ready to push"; the read-only pass records
`read_verified_at`, which is a weaker claim and is named like one.

> A justification attaches to a specific property, and a call that bundles
> several properties inherits the weakest justification anyone wrote for it.

## Removing a fallback that had never yet been wrong

`push_hook()` read the list's `remote.json`, and fell back to the global
`nsot_git_remote_url` for a list that had none — so that an installation which
had not adopted yet kept working.

Harmless today: the global is empty. But a global URL cannot express one
repository per network, which is the entire reason for per-list configuration.
A second list without its own `remote.json` would have pushed into whatever
repository the global happened to name — one network's history landing in
another's, silently. The fallback reintroduced the failure the design exists
to prevent, for precisely the lists that were not yet configured.

The rule is now unconditional: **no `remote.json`, no push.** The setting key
is not deleted — settings keys never are — it is simply not read. A test sets
a non-empty global, gives the list no `remote.json`, and asserts the hook does
not reach `git` at all; another asserts structurally that the hook's source
mentions none of the global keys.

Worth noticing what made the fallback attractive: it was written to avoid
breaking something, and the thing it avoided breaking did not exist. There is
no installation with a configured global and an unconfigured list. It was
compatibility with a hypothetical, bought at the price of the property the
whole phase is for.

## 1656 tests, and not one of them parsed the JavaScript

The Remote card shipped with a single-quoted string spanning a line break:

```js
kinds.map(k => `  ${k} x${counts[k]}`).join('
') +
```

The browser rejects the entire script element on a parse error, so it
discarded the **Baselines loader** along with it. The newest and least
important card on the page took out the oldest and most consequential one —
the panel that says which baselines would re-publish dead credentials and lock
the tool out of the switches.

Server-side everything was fine: endpoints 200, markup present, no log errors.
The failure existed only in a parser nothing in this project runs.

### How it got written

The JavaScript was authored inside a Python string. In a non-raw Python
string, `\n` **is** a newline, so `.join('\n')` in the source became
`.join('` + newline + `')` in the output. Backtick template literals in the
same block survived the same treatment, because they legally span lines — so
most of the transformation looked fine, and one quote style did not.

Two languages, one escaping layer between them, and the layer silently agreed
with the generator about `\n` while disagreeing with the target.

### Three fixes, in order of what they buy

**The string.** Built as an array and joined, so no literal spans a line at
all — rather than escaping it correctly and depending on the next author to
notice.

**Isolation.** The Remote card is its own script element now, and the call
into it is guarded with `typeof`. A parse error still kills its own block, but
the Baselines panel renders regardless. `try/catch` cannot help here: a parse
error happens before any statement runs, which is exactly why the failure was
total rather than local.

**A test that runs the parser.** `node --check` on every inline script when
node exists — and node is installed on neither the development machine nor the
deployment host, so a scanner in pure Python does the same narrow job
unconditionally. It tracks comments, template literals and regex literals well
enough not to cry wolf on `/[&<>"']/g`, and reports any quoted string opened
and not closed on its line. Run against the shipped commit, it flags lines
304–305 and refuses it.

> A test suite that checks generated code by searching it for substrings has
> not checked that the result is a program. Every language in the repository
> needs something that parses it, and "we have 1656 tests" says nothing about
> the one that has no parser pointed at it.

The narrowness of the scanner is deliberate. A general JavaScript parser in
Python would be a dependency and a maintenance burden for a project that
vendors its front-end precisely to avoid those. This checks one defect class,
runs everywhere, and cannot be skipped into uselessness — which the node check,
skipped on both machines that matter, would otherwise have been.

## The consumer ran before its own container existed

The Remote card was in the served page and was never called. No console error,
no request in the log, a blank space where the card should be.

The hypothesis was script ordering: three blocks now, and the caller's
`typeof` guard would be false if the card's block had not defined its function
yet. Plausible, and wrong — the card's block is second and the caller's is
third, so the symbol existed.

The ordering that mattered was *inside one function*:

```js
async function loadGoldenRepoPanel() {
  ...
  if (typeof loadRemotePanel === 'function') loadRemotePanel();   // line 402
  ...
  host.innerHTML = `
    <div id="remotePanel"></div>                                   // line 408
```

The call ran six lines before the container it renders into was created.
`getElementById` returned null, and `loadRemotePanel` did what it had been
written to do with a missing element: `return`.

### Every guard here made it quieter

The `typeof` guard was added so a broken card could not take the Baselines
panel down. It worked — and it also meant a card that failed for an entirely
different reason failed **silently**. The early `if (!host) return;` is the
same shape: written for the case where the panel is not on screen, it
swallowed the case where the panel was on screen and the container was not
built yet.

Three defensive patterns, each sensible alone, composing into a component that
could not report its own absence.

### An empty div can only look like success

The structural fix is not about ordering at all. The container is now
**server-rendered, with text in it**:

```html
<div id="remotePanel">
  <div class="alert alert-warning">Remote card did not load — see the browser console.</div>
</div>
```

A card that never runs now leaves a message; the script replaces it on
success, and replaces it with an error on a failed fetch. Nothing
distinguished "not loaded" from "loaded and empty" before, and the operator
had to read the server log to find out which.

The card also initialises itself on its own `DOMContentLoaded` rather than
being called from another block. A component that depends on another
component's internal call order is not isolated, whatever else was done to it
— and "guarded with `typeof`" is not isolation, it is a quieter coupling.

> Defensive code that returns early on a missing precondition is asserting the
> precondition is optional. When it is not optional, the early return converts
> a defect into an appearance.

Seven of the ten new tests fail against the shipped state and pass now.

## A check that could only ever refuse, and a reason nobody could read

Two defects in one screenshot, taken in the split second before the output
vanished.

### The list was its own rival

```
[XX] not_another_lists_repo — list 'default' already pushes to dmarchak/rcn-nsot-config
```

The cross-list uniqueness check walks the lists directory and skips the list
being verified:

```python
for slug in sorted(os.listdir(lists_dir)):
    if slug == list_name:
        continue
```

`get_current_list_name()` returns the **display name** — `Default` — and the
directory is the **slug**, `default`. The skip never fired, so the list found
its own `remote.json` and reported itself as the other network that already
owns the repository. No adopted list could ever pass verification, and the
message said something that is both true and useless: `default` does push
there, because it is the list you are verifying.

The comparison was of two strings that usually match. It is now of two
resolved data directories, which answers "is this the same list" — the
question — rather than "do these spellings agree", which was never it.

The same display-name/slug split has now appeared three times in this project
(the pipeline's `get_current_list_name()` after a push, `restore`'s
`_devices_of()`, and here). Each time the fix is the same shape: compare
identities, not names.

### The reason appeared for a split second

Every action on the card ends by refreshing the card, and the output area was
inside the markup that refresh replaces. So a result rendered, and a moment
later the refresh wiped it.

This is a worse failure than showing nothing. The operator saw that something
was said, and could not read it — which converts a diagnosable refusal into a
suspicion that the page is broken. It also made the first defect much harder
to find than it needed to be: the check's message named its own cause, and it
was on screen for less than a second.

The output area is now a **sibling** of the card, server-rendered, so a
re-render cannot reach it. Results are also kept in state and restored after
any render, carry a timestamp, and have a dismiss button; only the
"working…" messages are transient.

> Any region that is rebuilt wholesale will eventually destroy something
> important that was placed in it. Output that outlives an action belongs
> outside the thing the action refreshes.

## What the first push actually published

`dmarchak/rcn-nsot-config`, private, 61 commits, 1 branch, 33 tags, `main`
matching the local HEAD. The SNMP communities were acknowledged through the
UI by a verified person; auto-push is on.

The material in that history, measured rather than asserted:

| kind | count | state |
|---|---|---|
| plaintext router passwords | 5 | **dead** — rotated to type 9 |
| switch type-5 secrets | 4 | **dead** — rotated to type 9 |
| type-9 secrets | 9 | live, salted, not recoverable |
| SNMP communities | 9 | **live**, read-only, ACL-restricted, acknowledged |

**This is the reason every device was rotated before anything was
published.** A push is not a snapshot: it publishes every commit, so the
question was never "what is in the configuration now" but "what has ever been
in it". Rotating afterwards would have changed the devices and left the
history exactly as exposed — the credentials would have been dead on the
devices and perfectly usable to anyone who had already cloned.

So the ordering was not a preference about tidiness. Publication is
irreversible in a way rotation is not, and the only moment at which the
exposure could be reduced was before the push. Everything that survives in
that history is either dead, unrecoverable, or a read-only community somebody
read the count of and agreed to.

The communities remain the one live exposure, and the honest statement about
them is the one that justified acknowledging: v2c communities are cleartext in
every golden by design, so rotating them first would only have shortened how
long the published values stayed current. The real fix is SNMPv3, and it is a
Part 2 item rather than a condition of publishing.

### Queued: a resolved list reference

The display-name/slug split has now caused three separate defects — the
pipeline reading `get_current_list_name()` after a push, `restore`'s
`_devices_of()`, and the remote's uniqueness check comparing a list against
itself. Each was found only after it misbehaved, and each fix was the same
shape: stop comparing names, compare identities.

A `ListRef` resolved once at the edge, from either spelling, and passed
instead of raw strings would make the third recurrence the last. Same move as
making a leaf a type rather than a string. Queued deliberately rather than
done in passing: it touches every call site that takes a list name, which is
a change to make on purpose and not while finishing something else.

## The rule was a convention, because the default said otherwise

`resolve_identity()` cannot create an identity. That was made true
structurally, after a resolver that *could* mint trusted a supplied uid the
manifest had never seen and every deploy created a duplicate entry. Creation
lives in `adopt_identity()`, "called only by a caller that has decided this
really is a new device".

The gate in front of it was `save_golden(allow_new=True)` — a default.

Four of seven call sites took it: **Save All**, a pipeline golden save,
`config_git`'s manual save, and a path reachable from the **AI assistant**. So
a device that appeared in the inventory acquired an identity as a side effect
of the next routine capture. The answer to "when was this device onboarded"
was "whenever somebody next pressed Save All", and the caller least entitled
to create an identity was among those that could.

Nothing had gone wrong yet. Every identity minted that way was for a device
somebody had genuinely added. But the property being relied on was "no caller
does the wrong thing", which is a different and much weaker property than the
one the separation of `resolve_identity` from `adopt_identity` was built to
provide.

> A rule enforced by a parameter whose default breaks it is a convention. The
> default is the behaviour.

### What the flip exposed

Flipping to `allow_new=False` broke **71 tests across two files** — every one
of them a fixture seeding a fresh repository, which is genuinely onboarding
and now says so through a `_seed()` helper that passes the flag in one place.
No production caller broke, which is worth stating precisely: it means none of
the four was minting in the cases the tests cover, not that none of them
could.

The four now pass `allow_new=False` **explicitly**, along with the two that
already did. Stating a decision that matches the default looks redundant until
the default moves under you, which is exactly what this commit did to
everybody else.

### Where an identity is created now

**Add Device**, which is where onboarding actually happens for an existing
device, and where it had never happened: the form wrote a CSV row and left the
identity to whichever `save_golden` ran first. It now resolves by name and by
IP, mints through `adopt_identity()` only when neither finds anything, writes
the manifest entry, and records the uid on the CSV row — because an identity
nobody records is minted again next time.

**The onboarding wizard**, which does not exist yet. Phase 4 adds the second
and last one.

The AI assistant has a test of its own asserting it neither passes
`allow_new=True` nor names `adopt_identity` anywhere, plus a behavioural one
that an unknown device is refused with the reason. Structural and behavioural
together, because the structural check alone would pass a module that reached
minting through an import alias.

---

## The same character, twice, because the rule was attached to the wrong thing

An em dash has now broken this project in two places that shared no code:

1. **A pushed command.** `description NSoT-managed b` reached a device as
   three UTF-8 bytes where IOS expected one character. IOS consumed the first,
   lost sync, and truncated the line. Netmiko then failed on an echo mismatch,
   so what surfaced was a *timeout*, and nothing in the message pointed at the
   character.

2. **A comment in a startup config.** `docs/bootstrap-probe/configs/bp-vios.cfg`
   carried explanatory comments, one of which used an em dash. The node hung
   during boot and never reached "Startup complete".

The fix for (1) was `assert_sendable()`, and it was correct. What was wrong
was where it lived: on the **deploy path**, guarding a *command list* about to
be pushed. A startup config is not a command list, so nothing checked it.

### Why the second one was invisible until a specific platform hit it

The probe deployed both platforms with configs written the same way. The
C8000v booted fine. The vIOS hung.

The difference is in how vrnetlab applies a startup config per kind. For the
C8000v it is `gen_bootstrap_config() + startup_cfg` handed over as a **file** —
the bytes are never parsed a line at a time by a CLI, and a comment is just
bytes in a file. For vIOS there is no such path, so the launch script **types
the config into the console**, line by line, waiting for a prompt after each
one. Every line is a CLI interaction, including the comments. The line
beginning `!` never produced the prompt it was waiting for, and the boot
stopped there.

So the same content is inert on one platform and fatal on the other, and no
amount of testing the first one finds it. A rule scoped to "the deploy path"
was never going to cover this, because the thing that made a comment dangerous
was not what the file *was* — it was what a particular launch script *did*
with it.

### The rule, restated

**Anything that reaches a CLI is printable ASCII — comments included.** Not
"commands we push". Not "the deploy path". The boundary is the CLI, and a
comment crosses it whenever something replays the file through a console.

`modules/nsot/bootstrap_config.py` is where that is now enforced for generated
configs. It runs `assert_sendable()` over the **entire rendered text**, not
over a filtered subset — a guard applied to "the commands" would pass exactly
the file that hung the boot. `test_bootstrap_config.py` asserts the guard runs
on `text.splitlines()` and not on anything narrower, because "we check the
output" is a claim that stays true while the thing being checked quietly
shrinks.

On console-replayed platforms the generator emits **no prose comments at all**
(`CONSOLE_REPLAYED`). Bare `!` separators stay — IOS emits those itself, so
removing them would make the capture differ from the file — but commentary
goes. This is not caution about the character; it is that every line costs a
console round trip and is a chance to desync, and a comment buys a device
nothing. The explanations live in `docs/bootstrap-probe/README.md`, which
nothing types into a console.

### One generator for the probe and the wizard

The probe measures what the wizard will emit, or it measures nothing. That
only holds if they are the same code, so `render_bootstrap()` is the single
producer and the probe's fixtures are compared against it directly
(`TestItMatchesTheMeasuredProbeConfigs`) — every non-comment line, byte for
byte. Two files that happen to agree today are two files that will disagree
later.

The generator also carries the two platform asymmetries the probe established,
rather than leaving them as facts in a document:

* **`VRNETLAB_INJECTS_USER`** — on IOS-XE, vrnetlab applies
  `username admin privilege 15 password admin` *before* the startup config, so
  a `secret` line for the same user is refused with
  `ERROR: Can not have both a user password and a user secret` — the same
  refusal measured on r2 during stage 1. `secret_clause()` emits the password
  form there and the secret form on vIOS.
* **The management interface** — absent on the C8000v because vrnetlab owns
  it; configured explicitly on vIOS because with
  `CLAB_MGMT_PASSTHROUGH=false` nothing else gives it an address. A generator
  that treated both platforms alike would produce an unreachable switch.

An unknown platform raises `UnsupportedPlatform` with a message saying to
measure a fresh node rather than write a guess. That is the whole point of
having a probe: the bootstrap profile is measured, and a platform nobody has
booted has no profile.

### The scope of the ASCII test

`TestEveryProbeFileIsAscii` walks `docs/bootstrap-probe/configs/` only — the
files that reach a node. The topology YAML is read by containerlab's parser
and the README by people; neither is a CLI. Widening the rule to them would
turn a safety property into a house style, and a rule that fires on prose is
a rule people learn to ignore.

---

## Headline finding: a presence check that passed while the property was false

**Measured on hardware, 2026-09-21.** Five production routers would have come
up unreachable at the next redeploy, and every check the system had said they
were fine.

### What was true

`configs/r1.cfg`–`r5.cfg` each carry
`username admin privilege 15 secret 9 $9$…`, written by the stage 1 credential
rotation. The persistence chain verified that by reading the startup file back
and finding the hash in it. It was there. The check passed, correctly.

vrnetlab's patched launch script builds the config it applies as

```python
cfg = self.gen_bootstrap_config() + startup_cfg
```

and `gen_bootstrap_config()` contains
`username admin privilege 15 password admin`. So vrnetlab's line is applied
**first**, and IOS-XE refuses a secret for a user that already has a password.

### What the boot showed

A throwaway C8000v booted a startup file in exactly r1's shape:

```
%AAAA-4-...            (type-0 warning for vrnetlab's injected line)
%CVAC-4-CLI_FAILURE: Configuration command failure:
  'username admin privilege 15 secret 9 $9$…' was rejected
```

After boot, `show running-config` held
`username admin privilege 15 password 0 admin`. Over SSH, `admin` was
**accepted** and the startup file's own credential was **refused**.

`Startup complete` was reached in 7m26s. The container reported healthy. The
router answered SSH. **Nothing failed.**

### Why this is the dangerous shape

The defect is not that a check was weak. `verify_startup_file()` asked "is the
new hash in the startup file", and the answer was yes, and the answer was
*correct*. The question was the wrong one: what matters is not whether the
hash is in the file but whether **the file applies**. Presence and
applicability are different properties, and here they diverged completely —
presence true, applicability false, for all five routers at once.

A reviewer reading that check finds nothing wrong with it, because there is
nothing wrong with it. It cannot be found by reading. It was found by booting
a node that could be thrown away.

And the failure it was guarding against is silent by construction. A redeploy
would not error. It would produce five healthy routers holding credentials
nobody has, with startup files that read correctly, and the first symptom
would be NMAS failing to log in to all five at once — after the state that
could have explained it was gone.

### The correction

**A check about a remote system's behaviour has to exercise that behaviour.**
This is the same lesson as the rotation verifier reporting a local
`InvalidToken` as a device verdict, arriving from the opposite direction:
there, a local fault was reported as a remote answer; here, a local
observation (bytes in a file) was accepted *as* a remote answer. Both are the
same substitution — reading something nearby instead of asking the thing
itself.

`verify_startup_file()` becomes an **applicability** check. It can be done
without redeploying production, because the platform's launch path is known:
on a C8000v, a `username <vrnetlab-user> … secret …` line in a startup file is
unappliable, full stop, and the chain knows the platform. That rule is cheap,
runs on every rotation, and would have fired the moment the first router's
file was written.

The ban on redeploying rcn-lab1 now rests on this measurement rather than on
a reading of the launch script, and is recorded in three places — `CLAUDE.md`,
`docs/bootstrap-probe/README.md`, and `docs/NSOT_PHASE4_ONBOARDING.md` — all
of which say **confirmed**.

### Stage C, and what a pass would license

Fix (a) is a second line in the launch patch rcn-lab1 already binds: skip
vrnetlab's injected `username` line when the startup config defines that same
user. `patches/patch-skip-injected-user.py` applies it against a copy, prints
the real diff, and refuses if the file is not what stage B measured — a patch
written against a file the author could not read is a guess with line numbers
on it.

The question stage C actually has to answer is not whether the secret lands.
It is whether **vrnetlab still needs the account it injects**: it authenticates
to the console with `--username/--password`, and the healthcheck may too. So
stage C is two boots, not one. C0 skips the injection while leaving the device
holding the credential vrnetlab was given; C1 changes it. C0 passing and C1
stalling is the precise signature of "vrnetlab needs its own account", and a
single boot could not tell that apart from "the patch is broken".

A C1 pass would not lift the ban on its own. It would license adopting the
patch, which is a different thing from having adopted it — the applicability
check has to be in place first, so the next rotation cannot recreate this
silently, and the five routers' current credentials have to be recorded
somewhere that survives those routers being unreachable.

---

## Stage C: the fix proven, and the ban still standing

**Measured on hardware, 2026-09-21.** The same startup file stage B booted
(sha256 verified identical), with a launch script carrying the user-skip:

| observation | value |
|---|---|
| Startup complete | reached, 7m15s |
| the patch | fired — `startup config defines admin; not injecting vrnetlab's own username line` |
| CLI failure for the username line | **none** |
| running config | `username admin privilege 15 secret 9 <hash>` |
| SSH with the file's own credential | **accepted** |
| SSH as `admin` | **refused** |

Stage B and stage C differ in exactly one input — the launch script — and the
outcome inverts completely. That is what makes it evidence rather than a
coincidence: the same bytes, the same image, the same node type, one variable.

### The health reading that was not a finding

A `docker inspect` three seconds after `Startup complete` returned
`unhealthy`, and it would have been easy to write that up as a cost of the
patch. It is not one, and the reason is worth recording because the temptation
was to reason about it rather than look.

The image's `/healthcheck.py` reads `/health` and exits with its status. It
performs no login and holds no credentials, so there is no mechanism by which
skipping a username injection could change what it reports. The `unhealthy`
was Docker's own stale result from the boot period — default 30s interval,
three retries — read before the first post-boot probe had run. `rcn-lab1-r1`,
the same image, reports healthy.

Two independent checks, either of which settles it: the healthcheck's source
(no credential path exists) and a control (the same image healthy elsewhere).
A single observation with no control is what produced the withdrawn Oxidized
conclusion earlier in this project.

### A second defect, found only because the first was fixed

```
%CVAC-4-CLI_FAILURE: Configuration command failure:
  'ip domain-name rcn.lab' was rejected
```

IOS-XE 17.6 spells it `ip domain name`; classic IOS spells it `ip domain-name`
and rejects the spaced form. There is no spelling that works on both, so the
generator has to know the platform.

This one was invisible for the same reason as the first: **the node booted,
was healthy, and answered SSH with no domain name set.** Nothing downstream of
a rejected global asks whether it applied. It would have surfaced at r6, as
something else failing — a `crypto key generate rsa` with no domain name, most
likely, reported as a prompt rather than an error.

Both defects are in the same class as the headline finding: a config line that
is present, well-formed, and silently not in effect.

Production router startup files come from Oxidized, i.e. from each device's
own `show running-config`, so they carry IOS-XE's own spelling and are
probably unaffected. **Probably is not measured** — one grep of
`~/labs/lab/configs/r*.cfg` settles it, and it is reported, not acted on.

### What stage C licenses, and what it does not

It licenses *adopting* the patch. It does not lift the ban, and the ban is
recorded as still standing in all three places.

Proven on a throwaway node is not adopted here. Four things are needed, and
all four are future work:

1. the patch adopted into `~/labs/lab/patches/c8000v-launch.py` — the file
   r1–r5 already bind;
2. the static applicability check live in the persistence chain, so the next
   rotation cannot recreate the hazard silently;
3. r1–r5's credentials recoverable while the routers are unreachable;
4. the generator fixes above.

Items 2, 3 and 4 are **built and tested** (`verify_startup_applies()`,
`modules/breakglass.py`, `DOMAIN_KEYWORD` / `GENERATES_SSH_KEY`) and none of
them has been adopted into the lab. Built is not deployed, and a plan that
treats the two as the same thing is how a redeploy happens by accident.

---

## A named pattern: prose about code is not code

Three false positives in one stage, each a test that **passed while the thing
it claimed to check was broken**. All three had the same shape: a test read
`inspect.getsource()` and searched the text.

`inspect.getsource()` returns the docstring and the comments as well as the
code. So a test that greps it is searching the *explanation* of the code
alongside the code — and an explanation that mentions the forbidden thing
satisfies a search for the forbidden thing.

| test | what it searched for | what actually matched |
|---|---|---|
| "`save_host_vars` is called once" | `source.count("save_host_vars(")` | the **comment** saying it commits once |
| "break-glass never reads `data/key.key`" | `"key.key" not in source` | the **docstring paragraph** explaining why it must not |
| "Save All calls `save_golden` once" | `source.count("save_golden(")` | a **docstring** naming `save_golden()` |

The second is the sharpest. The module's docstring argues at length that
encrypting with `data/key.key` would make the record share a failure with the
thing it recovers — and that argument is what tripped the test written to
enforce it. The better the explanation, the more likely it breaks the check.

The first is the most expensive. It passed on a script that **could not run at
all**: `write_committed()` was called with the wrong arity, every structural
assertion about the call site was true, and `--write` crashed on its only real
invocation.

### The fix, and the lesson separately

The fix is `calls_in()` — parse to an AST, walk it, count `ast.Call` nodes
whose target matches. Docstrings and comments are not in the tree.

The lesson is larger than the helper, because the helper only covers calls:

> **Searching source text searches the prose too.** A codebase that explains
> itself well has more prose to trip over, so the discipline that makes the
> code readable is the same discipline that makes text-matching tests
> unreliable. Ask the parsed structure, or run the thing.

The same reasoning is why the three graded UI paths are tested by *executing*
the helper with dukpy rather than inspecting it, and why the `--write` path
now runs end to end against a real git repository. A structural test can
confirm the shape of code that does not work; only running it can confirm it
does.

**Where text matching is still right:** asserting what a page *says*. The tab
descriptions (1.6) are checked as rendered text on purpose — the claim there
is about the prose, so the prose is the subject rather than the noise.

### The fourth instance landed inside the test written to confirm the third was fixed

Worth stating on its own, because it is the clearest the pattern ever got.

`check_right_repository()` compared `slug == list_name` — `'default'` against
`'Default'` — so every adopted list failed its own uniqueness check. The fix
was `ListRef.matches()`, comparing identity rather than two different names.

The test written to confirm that fix:

```python
source = inspect.getsource(remote.check_right_repository)
assert "matches(" in source
assert "slug == list_name" not in source
```

It failed **on the corrected code**. `slug == list_name` is in the comment
that explains the defect:

```python
# ... so `slug == list_name` was false for the very list being verified —
# and every adopted list failed its own uniqueness check ...
```

So the assertion written to prove the bug was gone was satisfied only while
the bug was **undocumented**. Explaining the fix broke the test that checked
it, and the better the explanation, the more certainly it breaks.

That is the whole pattern in one place: `inspect.getsource()` returns the
prose with the code, so a text search over it cannot distinguish a thing from
a description of that thing. `tests/astcheck.py` exists so the fix is one
import rather than a judgement call at each site.

---

## Coverage that was never designed, only inherited

The drift checker enumerates the devices it will check from
`ai_assistant._list_golden_configs()`, which lists
`data/lists/<slug>/golden_configs/` — the **legacy** store. Phase 2 made
`config_repo/golden/` the golden store and stopped writing to the legacy one;
`_find_golden_config_file()` still reads it as a documented fallback, so the
*content* the checker compares is resolved manifest-first and is current.

What is not current is the **list of devices**.

> All nine devices are drift-checked only because their legacy files predate
> the migration. The coverage is accidental. Nothing has maintained that
> directory since, so the set it describes is frozen at the moment migration
> ran.

Every device onboarded after that point is outside drift detection from
birth, and nothing anywhere reports it. The check does not fail for such a
device — it never considers it. A run that says "checked 9, all clean" is
indistinguishable from one that should have said "checked 9 of 10".

That is the third time this shape has appeared in one week:

| | reads as | actually |
|---|---|---|
| NetBox tab (1.6) | "unreachable devices are reported but not created" | nothing reaches out; an offline device is imported |
| Template preview (1.3b) | a clean diff | secret-bearing lines were never compared |
| Drift check | "checked 9, all clean" | 9 is the size of a directory nobody maintains |

Each is a **protection that reads as present because nothing says it is
absent**, and each was found by asking what a passing result actually
measured rather than whether it passed. The first two were found by reading
the code behind a claim. The third was found by asking a question about a
*different* subject — whether anything compares real secret values — and
following the answer past the point where it had already said "yes".

The fix in each case is to make the absence visible rather than to widen the
check: the tab names what it does and does not do, the preview counts the
lines it could not compare, and the drift run reports what it checked
**against what the inventory holds**. A count beside a count is something an
operator can act on. A clean result alone is not.

**Why it is a prerequisite rather than a follow-up.** r6 is the first device
this project will onboard after the migration. Onboarding it before this is
fixed produces a device outside drift detection from the moment it exists,
and the only signal would be a number that has always looked right.

---

## The check that passed because it never asked

Stage D2 cleared the switches. It also found a defect in the checklist that
was verifying it, and that finding is worth more than the clearance.

The line was:

```bash
sshpass -p 'admin' ssh ... && echo "FAIL: old credential works" \
                           || echo "PASS: admin refused"
```

The connection died at **key exchange** — a modern OpenSSH client against a
2018 vIOS image — so `ssh` exited non-zero and the check printed **PASS**.

It would have printed PASS with the device powered off. It would have printed
PASS with the cable pulled. And the production redeploy checklist carried the
identical line for item 5, the item the entire stage exists for: it would have
reported *"the routers refuse the old credential"* while every router sat on
`admin/admin` and unreachable — the precise hazard, announced as absent.

> **Exit status conflates "the device refused us" with "we never reached the
> device".** Those have opposite consequences, so they cannot share a verdict.
> A two-valued check on a remote system is a check that can pass by not
> asking.

This is the same defect as the rotation verifier reporting a local
`InvalidToken` as a device verdict, and the fix is the same one, already
built: `verify_new_credential()`'s `attempted` flag, which exists precisely to
separate "the device answered and said no" from "we never got far enough to be
told anything". `scripts/nmas-check-credential` returns three verdicts and
exits 2 on INCONCLUSIVE, so it cannot be mistaken for a refusal.

### The correction that matters more than the third value

The old check used the **shell's `ssh`**. The claim being made is *"NMAS can
log in to this device"* — and NMAS connects through Netmiko/Paramiko, which
still offers algorithms OpenSSH 9 dropped. The checklist was testing a
different client's ability to reach the device and reading the answer as if
it were about NMAS.

`connection_params()`'s docstring had anticipated this exactly — *"legacy KEX
or host-key algorithms for older IOS against a modern client"* — as a reason
to have one builder. The runbook reached past it to a shell command anyway.

> Test the property, not something adjacent to it. "Can NMAS log in" is
> answered by making NMAS log in.

### And a device that lied about its own uptime

During D2's first boot a vIOS took a CPU exception (PnP Agent Discovery,
SIGBUS) and **silently reloaded**. The container stayed healthy. `docker logs`
said nothing. Only `show version | include uptime` revealed it.

`Startup complete` had been printed — by the *first* boot. Every check keyed
on that line would have been reading about a boot whose result no longer
existed. The post-redeploy checklist now reads uptime per device, because a
node that reloaded after its config was applied is a node whose running config
may not be what the log says was applied.

Three findings in one probe run, none of them the thing the run was for.

---

## Correct reasoning about the wrong object

Twice in this project a confident, well-argued conclusion was drawn from an
artifact that was not the one in question.

**The GUI click-paths.** A hand-off listed the path to Deploy, Templatize and
Golden tabs. None existed. The paths came from the design documents, which
describe what the phases build, rather than from `templates/index.html`,
which describes what is on the screen.

**The switches' SSH keys.** Item 0 of the redeploy checklist claimed nothing
in s1–s4's startup files creates an RSA key, and concluded the redeploy would
return four switches with no SSH server. The reasoning was sound and the
evidence was real — two measured vIOS boots, from the same image, with
hostname and domain set and `ip ssh version 2`, that did **not** get an SSH
server.

But the evidence was about the **probe** configs. Those are minimal
bootstraps and legitimately lack `crypto key generate rsa`. The real switch
startup files contain it — s1 at line 187 — and s1's key is timestamped four
minutes after the deploy that created it. Generated at boot, by the file.

One `grep` of `~/labs/lab/configs/s1.cfg` answered a question that a page of
correct inference got wrong.

### Why this one is worth recording separately

The conclusion was **more alarming than the truth**. That direction feels
safe — it adds a check rather than removing one — and it is the direction
that costs a scheduled session and erodes trust in the next warning. A false
alarm and a missed defect are both wrong answers.

The tell was available and unread: every measurement supporting the claim
came from files in `docs/bootstrap-probe/`, and the claim was about files in
`~/labs/lab/`. **When every piece of evidence comes from one artifact and the
conclusion is about another, that gap is the thing to check first.**

It also corrected an earlier conclusion. Stage D2 had recorded that "SSH
needed a hand-typed key" — true of the probe, and stated as though it were
true of the platform. A property of a test fixture had been promoted to a
property of the system.

---

## Four controls that could not fail, in one stage

Each was introduced as the fix for a previous silent failure. Each was
verified only in the state where it passes. None was run against the state it
was built to detect until somebody tried.

| # | the control | what it was guarding | why it could not fail |
|---|---|---|---|
| 1 | `nmas-persist-credential --dry-run` as a negative control | that `startup_applies` refuses when the launch patch is absent | the dry run returns **before** entering the persist chain, so the stage never ran. Same output with the patch present or absent |
| 2 | `sshpass ... \|\| echo "PASS: admin refused"` | that the old credential stops working after a rotation | the connection died at **key exchange**, so `ssh` exited non-zero and the check printed PASS. It would print PASS with the device powered off |
| 3 | `assert save_golden(...)` counted in `inspect.getsource()` | that the repair makes one commit | the count matched the **comment** saying it commits once, on a script that could not run at all |
| 4 | `LAUNCH_SKIP_MARKER in patch["text"]` | that the launch script skips its username injection | `_skip_users_defined_in_startupX` **contains** `_skip_users_defined_in_startup`, so renaming the helper — the obvious negative control — left the check passing |

The fourth is the one that mattered. It ran against the live host with the
marker renamed and reported **APPLIES for all five routers**, with the same
reason text naming the helper. Nine APPLIES lines were about to enter a
redeploy as evidence that the hazard was handled.

### The shape

> Every one of these was **the fix for a silent failure**, written by someone
> who had just been bitten and was being careful. Care is what produced them;
> care is not what validates them.

A check is a claim about a property. Running it where the property holds
tests the *claim*, not the check — the two are indistinguishable from a green
result. The only evidence that a check measures anything is watching it
**fail when the property is false.**

That is the same argument as "measure, don't infer", turned on the
instruments: a reading is only worth what the instrument is worth, and an
instrument that has only ever been used on a known-good sample has not been
calibrated.

### And the fourth was a presence check

`verify_startup_applies()` exists because `verify_startup_file()` asked "is
the hash in the file" when the question was "does the file apply". Its own
launch-script check then asked "is this name in that file" when the question
was "does the concatenation go through that helper" — the identical
substitution, one level up, inside the function written to correct it.

Three ways the name was present while the property was false: the renamed
identifier containing the original; the helper defined with the call site
reverted; a comment mentioning it. The check now requires the call **and** the
absence of the unpatched form, and reports the host, path and sha256 of what
it read — because a verdict about a remote file that does not say what it
looked at is a verdict nobody can check, least of all in a session where the
operator has just edited that file.

### What changed as a practice

The negative control is not an extra step after the check works. It is the
step that determines whether there is a check at all, and it belongs in the
suite rather than in a runbook — a control that lives only in a document is
run once, by someone who already believes the answer.

---

## The redeploy: what four days of measurement bought

The rcn-lab1 redeploy ban was lifted on 2026-09-22 by a successful redeploy.
It is worth recording what the alternative looked like, because the whole
sequence began with a line in a launch script that nobody had any reason to
read.

**Had the redeploy happened on 2026-09-21**, before any of this: all five
routers come up on `admin/admin`. Every one reports `Startup complete`. Every
container reports healthy. Every router answers SSH. The startup files still
say `secret 9`. NMAS cannot log in to any of them, and the first symptom is
nine devices' worth of automation failing at once, with the state that
explained it already gone.

**What it took to know that**, in order:

| stage | question | answer |
|---|---|---|
| A | what does a fresh node look like? | captures for both platforms |
| B | does r1's current startup file apply? | **no** — `%CVAC-4-CLI_FAILURE`, node healthy on the wrong credential |
| C | does the user-skip fix it? | **yes** — same file, one variable changed, outcome inverted |
| D2 | has a vIOS ever booted a `secret 9` line? | **no** — every prior proof was a C8000v |
| — | the redeploy | all nine correct, zero rejections |

Each stage answered one question on a node that could be thrown away. None of
them was expensive. The first one took a day to arrange and every one after
was under an hour.

### The things that were nearly wrong

**Stage D2 existed because the question was asked.** The switches were
rotated the same day as the routers and their startup files carry the same
shape — and nothing had ever fed a pre-computed `$9$` hash back to the
platform that emits it. Without D2 the redeploy would have been the first
test of four switches at once, which is precisely what stage B had just
taught.

**The applicability check reported APPLIES with the marker hidden.** It
searched for the helper's *name*; the renamed identifier still contained it.
Nine APPLIES lines were about to enter the redeploy record as evidence that
the hazard was handled. It was caught because the negative control was
actually run, on the real host, against the state where it should fail.

**Item 0 was withdrawn as false.** It claimed the switches would lose SSH
because nothing in their startup files creates an RSA key. Every one of them
contains `crypto key generate rsa modulus 2048`. The claim was reasoned from
the probe configs — minimal bootstraps that legitimately lack the line —
rather than read from the files the redeploy uses. Correct reasoning about
the wrong object, reaching a conclusion **more alarming than the truth**,
which is the direction that costs a session.

### What the result actually says

`758d1f56` — the post-redeploy Save All — changed **certificate bodies on
r1–r5 and nothing else**. Zero non-certificate lines across nine devices.
That is the strongest available statement that each node came back as itself:
not "the redeploy succeeded", but "the network is byte-identical to what was
captured before it, apart from self-signed certificates that are regenerated
on every boot by design".

The guard that keeps it that way is not the patch. It is
`verify_startup_applies()`, refusing a `secret` line in a startup file on a
platform whose launch path injects a password first — **at the moment the
rotation would create it**, rather than at the next boot, which is when the
original defect would have been discovered.

---

## The interface can deploy intent it cannot author

Stage 3.1 asked whether committed intent can be edited from the GUI. The
measurement: **`/templatize` appears zero times in the rendered page** — not
as a fetch, not in a dynamically built URL, not at all. Twelve routes,
unreachable:

```
POST /templatize/extract/<host>           POST /templatize/commit/<host>
GET  /templatize/committed/<host>         POST /templatize/committed/<host>
POST /templatize/committed/<host>/revert  GET  /templatize/rendered/<host>
GET  /templatize/report                   GET  /templatize/rolled-back
POST /templatize/rolled-back/<host>/retry
```

Measured the same way, for contrast: `/netbox/` appears 8 times, `/ai/` 28,
and `/deploy/plan`, `/templates/preview`, `/golden/history`, `/remote/status`
and `/monitoring/stack` once each. The method sees dynamically built URLs, so
this is absence, not a detection failure.

### Why this is different from the other unreachable code

Four times before, a working backend shipped with no button, and each time
the fix was a button. This is the same shape and a different size, because of
what sits on either side of it.

Phase 3c's central rule is that **a change is made by editing committed
intent and committing it**, never by configuring the device and
re-extracting. That rule is what makes the golden repo a source of truth
rather than a backup. It describes an operation with no path through the
interface.

Meanwhile "Deploy plan" *reads* committed intent, and has had a button since
Stage 1.5. A device with no committed intent is `bootstrap` and refused.

> So the interface can push a change toward a target it has no way to set.

The capability is built, tested and correct — `write_committed()` refuses a
resolved secret structurally and by value, `save_host_vars()` commits it,
`revert_committed()` applies the inverse of one commit's own diff. All of it
is reachable by `curl` and by nothing else.

### What it says about the other findings

3.3's legacy readers are correctness bugs: something reads the wrong store
and gives a stale or narrow answer. They are worth fixing and none of them
stops a person doing their job.

This one is a **missing capability at the centre of the design**, and it was
invisible for the same reason the others were: every test asked whether the
code works, and the code works. Nothing asked whether anybody can reach it.

`test_blueprint_reachability.py` now asks that of every route module written
to serve the interface, with `templatize` as its single allowlisted entry and
a test that the entry leaves when the editor is built. It is the
route-level twin of `test_no_unreachable_ui.py`, and it exists because the
function-level version would never have caught this: the functions it would
have checked were never written.

---

## A guard that missed the bug it was written for

While building the intent editor, a test fixture called
`save_golden("lab", ...)` **before** monkeypatching `get_list_data_dir`. That
function resolves its own path, so the call wrote
`data/lists/lab/config_repo/golden/s4.cfg` into the working checkout and
committed it — three commits, in a real repository, from a test run.

The list name was arbitrary. Had it been `default` it would have written into
the live list, whose goldens are the record of a real network. `data/` is
gitignored, so nothing would have reached a commit in the project repo and
**nothing would have said a word**.

The rule this needed is one the project already has, pointed at the other
thing a test can reach: *no test touches a live network* → *no test writes
into live data*. `tests/conftest.py` now fails any test that creates a file
under `data/lists/`.

### And then the guard did the same thing

Its first version compared the set of **list directory names** before and
after each test. Re-running the fixture bug against it: **19 passed.**

`lab` already existed, so writing a new golden into it changed no name. The
guard was checking a property adjacent to the one that mattered, and it
would have reported clean on the exact defect it was written for — including
on `data/lists/default`, which exists on every machine.

It compares the set of **files** now, and that version was verified by
reintroducing the bug and watching it fail.

> This is the four can't-fail controls again, in a fifth place, written
> immediately after recording the pattern. A guard is a claim about a
> property; running it where the property holds tests the claim. **Shown
> failing, or it means nothing.**

The interval between writing that lesson down and repeating it was about two
hours, which is the useful part of the observation: knowing the rule is not
the same as having a habit that enforces it. The habit is *reintroduce the
bug and watch*, and it takes under a minute.

### It took a third version, and then it found three more

The name-based version missed a file written into an existing list. The
file-based version missed a list directory created **empty** —
`get_list_data_dir()` calls `os.makedirs()`, so merely *resolving* a path for
an unknown list leaves one behind. Each caught what the other missed, which
is the argument for the union rather than for picking between them.

The union version then found three offenders nobody was looking for:

* `test_baseline_tag_push.py` — `record_push()` calls `save_remote()`, which
  the fixture never patched, so the push tests wrote a real `remote.json`
  into `data/lists/lab/`;
* `test_credential_rotation.py` — `plan()` calls `platform_of()`, **added in
  Stage 1.7**, which resolves the list's CSV and therefore creates the
  directory. A change that looked purely additive gave a pure function a
  filesystem side effect;
* `test_netbox_inventory.py` — the dispatch tests name a list that does not
  exist.

Only the first offender in a run was visible, because every later one found
the directory already there. The guard now **removes what a test created**
before reporting it, so one pass names them all.

The last of those needed the patch to go where the name is **bound**:
`modules/inventory` does `from modules.config import get_list_data_dir` at
module level, so rebinding `modules.config.get_list_data_dir` leaves its copy
untouched. Patching `LISTS_DIR` works either way, because
`get_list_data_dir()` reads that global at call time — and it preserves the
real per-list layout, which replacing the function did not.

---

## A verdict about a store, produced without consulting it

The first real run of the edit-commit-deploy loop was blocked at the first
step. Opening **Edit intent** on `s4` reported:

> Valid. Not deployable: template `cisco_ios/base.j2` is not approved for
> this device

The template had been approved. Nothing had edited it, no device had been
onboarded or removed, and the scheme had not changed. It read as an approval
that had revoked itself overnight — which is the precise failure the scheme-2
correction exists to stop, so it looked like that correction had come undone.

It had not. The sentence was never about the approval store.

`build_artifact()` takes `template_approved` as an ordinary keyword argument
and **defaults it to `False`**. `render_artifact.py` turns a `False` there
into that exact sentence. The new intent-editor route called
`build_artifact()` directly and never called `approval.is_approved()` at
all — so the message was generated, in full confidence and with the template's
name in it, by a code path that had not looked at the approval store.

This is the same shape as the presence-vs-applicability findings, one level
up. A check that is never run does not produce "unknown" or an error; it
produces the *default*, and the default is rendered in the same words a real
negative would use. The operator cannot tell them apart, and the more
carefully the negative is worded — naming the template, naming the device —
the more it reads like a measurement.

The fix is `routes/templates.artifact_for()`: the one place an artifact is
paired with its approval, used by both the template preview and the intent
editor. Tests assert that both routes call it and that building directly
does not happen.

### And the fix carried the same class of error in its comment

Reviewing it found a second defect. `artifact_for()` built the artifact, read
its parsed `host_vars`, passed `{hostname: host_vars}` to `is_approved()`,
and then built a **second** time — with a docstring stating that the order was
*forced*, "because `is_approved()` is keyed on the device's parsed
host_vars".

It is not keyed on them. `binding_fingerprint()` accepts `host_vars_by_device`
and deliberately ignores it, and **that ignoring is the scheme-2 correction**:
under scheme 1 a successful deploy changed the device's capture, moved the
hash, and revoked the approval that had authorised it. So the second build
served nothing, and a comment written while fixing an approval bug asserted in
prose exactly the dependency the approval code had been changed to drop.

Prose about code is not code — recorded here for the fifth time — but this
instance is worse than the earlier four. Those were tests matching a
docstring instead of a call. This one was a *rationale*: a future reader
restoring the coupling would have been doing what the comment told them the
system required. The three replacement tests are behavioural where they can
be (two different documents must ask the approval store the same question)
rather than structural only.

### The other two defects in the same report

Both were mine, both were in the reporting rather than the mechanism:

* **The line-number gutter rendered on top of the text.** CodeMirror measures
  character and gutter widths at initialisation; inside a Bootstrap modal
  that is still animating open, those measurements come back zero. It now
  refreshes on `shown.bs.modal` and again after the document loads, since
  either can be the later of the two.
* **"The document differs from what is committed, but the render does not"**,
  on a document nobody had typed into. The load *is* byte-for-byte — that was
  checked rather than assumed, because if it had not been, that would have
  been the finding. The route compared renders only, and my else-branch
  described the result as a document difference. It now returns
  `document_changed`, an actual byte comparison against the committed file,
  and the UI has three branches instead of two.

The third is the smallest and the most instructive: a message that asserts
something the code never measured, again. One function, two independent
instances of it, found on the same screen.

---

## Enumeration and content came from different stores

Stage 3.3's finding, and the one that makes the rest of it one decision rather
than four.

`ai_assistant._list_golden_configs()` was, in full:

```python
gdir = _get_golden_configs_dir()          # data/lists/<slug>/golden_configs/
for fname in sorted(os.listdir(gdir)):    # ...and nothing else
```

`_load_golden_config_file()`, next to it, resolved through the manifest:
identity, then management IP, then the legacy header scan. So the question
"which devices have a golden config?" was answered by the deprecated store,
and the question "what is device X's golden config?" was answered by the
repository. **Seventeen executable call sites across nine modules asked the
first question** — the drift checker, the event monitor, `check_runner`
(twice), `pipeline_builder`, `/templatize/report`, `/list/golden_configs`,
`scripts/nsot_first_runs.py` and six paths in the AI tool layer.

The nine reference devices were enumerable only because their pre-migration
files still sit in `golden_configs/`. **That coverage was inherited, not
designed** — and it was recorded as such after Stage 1, before anyone knew
what depended on it.

### What it would have done to r6

A device onboarded after the migration has a golden in `config_repo/golden/`
and no legacy file. Every one of those seventeen readers would have said it
has no golden config:

* the drift checker would not have checked it — not as an error, not as a
  skip, it simply would not have appeared;
* the event monitor would have raised "1 device has no golden config" about a
  device whose golden was sitting in the repository;
* Jenkins verification would have had no baseline for it;
* the AI agent would have been told it needs one and offered to create it.

None of that announces itself. "All 9 device(s) clean" over a ten-device
inventory is textually identical to the same sentence over a nine-device one,
which is why this survived Phase 3 in full view.

### The fix is one function

`repo.list_goldens()` enumerates the manifest, and `_list_golden_configs()`
became a thin adapter over it with an unchanged return shape. Fifteen call
sites were corrected without being edited; the two that were already right
(`routes/deploy` and `routes/templatize._captured_config`, both corrected
during Stage 1 for this exact reason) were left alone. `saved_at` now comes
from the commit rather than the file's mtime — the Stage 1.4 correction,
applied everywhere instead of at the one call site where it was noticed.

### And a retirement condition, because "deprecated" does not expire

Two things still read the legacy directory: the last link of
`_find_golden_config_file`'s chain, for a device whose management IP changed
outside NMAS, and the legacy-only entries in `list_goldens()`. Both can go
when nothing lives there that the manifest does not know.

`legacy_only_goldens()` measures exactly that, `GET /golden/legacy_store`
reports it, and the Golden tab says either "still holds N device(s)" with the
names or "can be retired". A deprecation with no exit criterion is a thing
nobody ever gets to delete, because the evidence for deleting it has to be
re-gathered by whoever next wonders.

---

## What a silenced check looks like six months later

The drift scheduler showed **Disabled** on the deployed instance. The cause
was a setting, not a defect, and switching it off had been right:
`drift_state.json` was written 2026-08-30 02:41, three minutes after a
scheduled run that reported drift on all nine devices, 69–164 diff lines
each, queuing an approval request for every one. That was during Lab 1,
before the NSoT work, when goldens were saved ad hoc and the comparison ran
against stale files. It was noise, and silencing it was the right call.

**The reason stopped holding weeks ago.** Goldens are committed and current;
the manual Check Now run on 2026-09-22 was 9/9 clean. Nothing anywhere
prompted a re-evaluation, and nothing would have.

That is the shape worth recording. The decision to silence a check is usually
correct at the time. What goes wrong is everything around it:

* **the state file was the only record the checker had ever been on** — a
  single JSON file in `data/`, not in git, with no note;
* **it recorded nothing about the switch itself** — not who, not when, not
  why. The date was recoverable only from the file's mtime, and the reason
  only by reading the stored last run and inferring it;
* **the panel blanked the "Last run" line while disabled**, so the thing that
  had been silenced was invisible in the one place somebody would look;
* **"disabled" and "enabled but nothing due yet" rendered identically** apart
  from a badge, both showing a null next-run time.

So the fix is not to refuse to silence checks. It is to make the silence say
when it started, who started it, and what the last thing it saw was —
`disabled_at`, `disabled_by`, the last run kept and shown, and a `state` field
that distinguishes **disabled** from **idle** from **running**.

Two real defects sat underneath, neither of which had fired:

* the state file was `DATA_DIR/drift_state.json`, installation-wide, while
  golden configs, approvals and the repository are all per list — so
  disabling drift for one network disabled it for every network, and the
  "last run" on any list's panel belonged to whichever list ran most
  recently;
* the scheduler's `finally` block handed `json.dump` a fresh three-key dict,
  dropping every key it did not itself write, `disabled` among them. It was
  unreachable while disabled so it never fired — but a switch that a
  completed run can silently flip is one bug away from switching itself back
  on, with no record in either direction.

**Re-enabling comes last, after the enumeration fix**, at the user's
instruction: re-enabling first would reproduce August — a scheduled job
producing alarms nobody trusts, whose fix is to switch it off again.

---

## The checker that could not be satisfied

Deleting `_scan_device` — 140 lines of SSH scanner with no callers — tripped
`scripts/check_removed_definitions.py`, which reported it as **GONE, still
referenced** and exited 1.

The references were:

1. `assert not hasattr(netbox_client, "_scan_device")` — the test pinning the
   removal;
2. the test module's docstring, explaining why it went;
3. a comment saying the same thing.

All three are the commit doing its job. A word-grep cannot tell them from a
call, so the gate would have reported GONE on every subsequent commit
forever. **A gate that cannot be satisfied is one that gets run with
`--no-verify`**, which is how a check stops existing — the same reasoning
already written into this script for the `_ios_error` and moved-helper cases.

So `_code_mentions()` parses instead of grepping: a use is an `ast.Name`, an
attribute access, an import alias, or a string constant (names reach
`getattr` and `monkeypatch.setattr` as strings) — but **not** a docstring,
**not** a comment, and **not** a string inside `hasattr`/`getattr`, which is
an existence probe. An unparseable file still counts as a reference, because
the conservative answer belongs on the side that reports.

This is **prose about code is not code**, arriving from the other direction.
The four earlier instances were tests that matched a docstring and passed
while the property was false. This one was a checker that matched a docstring
and failed while the property was true. Same cause, opposite symptom.

Two bugs were found in the fix itself, both by tests rather than by reading:

* `"_scan_device" in "_scan_device_from_golden"` is `True`, so the substring
  test reported every short name as referenced by the longer name that
  replaced it — which is exactly the pair it was first run against;
* `from mod import _gone` is an `ast.alias`, not an `ast.Name`, so the first
  version did not count an import as a reference. A file importing a deleted
  function is the least ambiguous referencer there is.

`tests/test_check_removed_definitions.py` exists because loosening a check
must not cost it its job: six tests assert a real caller is still found, five
that prose is not, three that matching is whole-word, two that an unreadable
file reports.

---

## A crash delivered as a successful redirect

Stage 3.3c added `actor` to `drift_check.set_disabled()` and left
`DriftChecker.set_disabled()` — the method the route actually calls — alone.
Every attempt to toggle the scheduler from the panel raised

```
TypeError: DriftChecker.set_disabled() got an unexpected keyword argument 'actor'
```

before touching the state file. Seventeen tests in `test_drift_scheduling.py`
passed throughout, because **every one of them called the module function
directly**. The path the operator uses was the one path nothing ran. It is
the same shape as the `write_committed()` crash in the 1.4 repair, and the
shared name is what makes it easy: editing `set_disabled` felt like editing
`set_disabled`.

The interesting part is not the `TypeError`. It is what the operator saw.

`@app.errorhandler(Exception)` redirected **everything** to the index page.
So the POST returned `302` — which `fetch` treats as success, following it
and receiving a page of HTML — the panel then refetched `/drift/status`, read
the unchanged `disabled: true`, and set the toggle back. A control that
silently reverts, nothing on screen, and the real error in a log the operator
had no reason to open.

That handler applies to every JSON route in the application. **Every
unhandled exception anywhere in the app was being presented to the interface
as a successful navigation.** The rule this project has written down since
Phase 0 — silent failure is the dominant failure mode, every call must
surface its failures — was defeated at the framework level by three lines
that predate all of it.

### Telling a navigation from a fetch

The handlers now redirect a browser navigation and return JSON with a real
status to anything else. The test is the **literal** `Accept` header, not
werkzeug's `accept_mimetypes`: for `Accept: */*` both `accept_html` and
`accept_json` are true with equal quality, so any comparison between them
picks a winner by tie-break rather than by evidence. A browser navigating
sends `text/html,…`; `fetch()` with no `Accept` header sends `*/*`. The
literal test separates them and nothing else does.

The error detail is redacted on the way out. The log is redacted by
`redact_all_handlers()`; an HTTP response is not, and it leaves the host.

### And the route stopped echoing its input

`/drift/settings` returned `{"disabled": <what you asked for>}`. A save that
did nothing therefore reported success, and the contradiction only appeared
one request later when the panel refetched the real state. It reports what is
**stored** now, read back after the write.

### What the grep for other callers turned up

Checking whether anything else called the functions 3.3c changed found
`agent_runner._run_drift_check`: **172 lines that are a second drift
checker** — its own enumeration, its own diffing, its own approval wording —
with zero callers, sitting a few lines below a comment reading *"Drift
checking is now handled by modules/drift_check.py … Nothing to do here."*

The decision had been made and only the code was left behind. It still
carried the pre-3.3b population, where a device with no golden config leaves
no trace at all, so wiring it up later would have quietly reinstated the
defect 3.3b was written to remove. Removed.

### The guard

`test_drift_routes.py` exercises the routes over HTTP — POST the toggle, GET
the status, assert the stored value changed — because a test that asserts the
*shape* of a call cannot see a signature that does not exist. It also
compares `DriftChecker.set_disabled`'s signature against the module
function's, and checks the method **forwards** what it accepts: a parameter
accepted and dropped is the same defect wearing a signature that type-checks.

Thirteen of the fifteen fail against the reverted code, including both
persistence tests, which reproduce the reported bug exactly. The one that
must pass under both — a browser navigation still gets its redirect — does.

While writing that guard I called `code_of("modules.drift_check",
"DriftChecker.set_disabled")`. It takes one argument. Inferring a signature
instead of reading it, in the test written about inferring a signature
instead of reading it.

---

## One file, three keys, three different lifetimes

An operator set `next_ts` to *now* in `data/lists/default/drift_state.json`
and waited. Two minutes later nothing had run and the log showed only
`/drift/status` polls.

The test was invalid, and the reason is worth more than the test would have
been. `drift_state.json` holds three keys that are read at three different
times, and nothing said so:

| key | when it is read |
|---|---|
| `disabled` | **every pass of the loop** — an edit takes effect within a minute |
| `last_check_ts` | **once, at process start**, to rebuild the schedule across a restart |
| `next_ts` | **never** |

The schedule is `DriftChecker._next_ts`, in memory. `__init__` computes it as
`last_check_ts + interval`; after that it moves only when a run completes
(`last_ts + interval`), when `trigger()` fires (*Check now*), when the
scheduler is re-enabled (`now + interval`), or when the interval is changed.
`_loop` compares `time.time()` against that attribute and nothing else.

So editing `disabled` works, and editing `next_ts` — two lines below it, in
the same file, written by the scheduler after every run — does nothing, for
ever, with nothing on screen to distinguish them.

**Writing a key nothing reads is what made the wrong conclusion reasonable.**
The operator had every reason to believe the file drove the schedule: one of
its keys demonstrably does drive behaviour, and another is read back at
startup. The scheduler no longer writes `next_ts`, `status()` reports
`next_from: "memory"`, and the panel's next-run time carries a title saying
it is held in memory and that *Check now* is the way to bring a run forward.

This is the same shape as the toggle that silently reverted, one level down:
an operator acting on the system, the system not acting, and nothing
anywhere reporting the disagreement.

### The 04:02:55 on the panel was real

It came from `set_disabled(False)`, which re-arms with `now + interval` — so
it dates from the moment the scheduler was switched back on, not from the
manual run at 03:32:40 and not from the file. With a 30-minute interval that
is 03:32:55 + 1800s. The panel was right; only the mechanism behind it was
undocumented.

### A note on observing it

**A deploy restarts the process, and `__init__` recomputes `_next_ts` from
`last_check_ts + interval`.** Deploying between arming the scheduler and the
run one is waiting for therefore moves the run. Any change to this module has
to be landed either before the arming or after the observation, which is an
awkward property of a scheduler whose state is half in memory, and the
clearest argument for the file being unambiguous about which half is which.

### And a sixth control that could not fail

The test asserting the scheduler no longer writes the key looked for
`'"next_ts"'` in `ast.unparse` output. `ast.unparse` emits single quotes. It
could not fail, in a test written about a key that was never read — so it
now walks the `ast.Dict` nodes and checks the actual keys, because the bare
string `next_ts` appears three times in that method as `self._next_ts`.

---

## The run that closed the loop

`scheduled 9 of 9`, 2026-09-23 04:03:14. It fired from the in-memory schedule
re-armed when the toggle was enabled — `now + interval` — not from the state
file, not from a button.

**It is the first scheduled drift check since 2026-08-30 02:38:48**, the run
that reported drift on all nine devices, 69–164 diff lines each, and queued an
approval request for every one. Three minutes later the feature was switched
off, and it stayed off for twenty-four days while five stages of NSoT work
went past it.

The comparison is the whole argument for the ordering:

| | 2026-08-30 | 2026-09-23 |
|---|---|---|
| Population | the legacy directory | the inventory |
| Baselines | ad hoc, saved by hand, stale | committed, current, one write path |
| Result | 9 drifted, 9 approvals queued | 9 clean |
| Coverage stated | no | `checked 9 of 9` |
| Outcome | switched off within three minutes | left running |

The same feature produced an unusable result and a useful one, and nothing
about the checker's diffing changed between them. What changed was what it
enumerated and what it was comparing against.

**Re-enabling was deliberately the last act**, after the enumerator (3.3a) and
the population (3.3b) were fixed, because re-enabling first would have
reproduced August exactly: a scheduled job producing alarms nobody trusts,
whose fix is to switch it off again. That is how the feature was lost the
first time. A silenced check does not come back by being remembered — it comes
back by someone making the thing it reports worth reading, and then enabling
it.

---

## Seven of eight decisions were never made

The security posture panel, on its first reading of the real install
(2026-09-23):

```
require_identity_for_reveal          ON   set explicitly
require_person_for_reveal            ON   defaulted (not in the file)
require_identity_for_approve         ON   defaulted (not in the file)
require_person_for_approve           ON   defaulted (not in the file)
require_identity_for_confirm         ON   defaulted (not in the file)
require_person_for_confirm           ON   defaulted (not in the file)
require_identity_for_publish_remote  ON   defaulted (not in the file)
require_person_for_publish_remote    ON   defaulted (not in the file)
service_allowed_operations           []   defaulted (not in the file)
```

**The posture is correct. One of the eight decisions was ever recorded.**

The other seven are right because the defaults happen to match what would
have been chosen — which is a different claim from *configured*, and until
this panel the two were indistinguishable by any means short of opening
`data/user_settings.json` over SSH and noticing an absence. An absence is a
hard thing to notice.

The one explicit entry is `require_identity_for_reveal`, written during the
D3 redaction work — the one occasion the decision was made deliberately at
the time, and the only one the file records.

### Why it was never written

`migrate()` returns early once the stored `settings_schema_version` has
caught up, and `SCHEMA_VERSION` is still 1. Every identity gate was added to
`DEFAULTS` after this install reached v1, so none of them was ever seeded.
`get_setting()` falls back to `DEFAULTS`, so everything worked, and nothing
anywhere reported that the file and the schema had diverged.

Measured directly: seed a store at v1, add a key to `DEFAULTS`, run
`migrate()` — `added_keys` is empty, the key is absent from the file, and
`get_setting()` returns its default regardless.

### The shape

A value believed configured, never written, indistinguishable from an unset
key — on the settings that decide **who may reveal a secret and who may
publish a network's history**. It is the silenced-check shape with the sign
reversed: there the concern was a protection switched off and nobody
noticing; here it is a protection that was never switched *on* in any
recorded sense, and nobody noticing either. Both are invisible for the same
reason, which is that nothing was showing the state.

**The panel is what made it distinguishable.** Not a fix — nothing was
broken, every gate was doing its job. It made a fact observable that had been
true and unobservable for as long as the settings existed. That is the whole
value of the thing, and it argues for building the observation before
assuming the configuration.

### And a trap sitting underneath it

`migrate()`'s v0→v1 block seeds **every** absent key in `DEFAULTS`, and it is
reached whenever `current < SCHEMA_VERSION`. Measured: with `SCHEMA_VERSION`
bumped to 2, a v1 install has **98 keys seeded in one pass, including all
eight identity gates**.

So the next schema-version bump — for any reason, about any unrelated
setting — would silently rewrite every "defaulted" as "set explicitly" across
every install, and the distinction this panel exists to show would be gone in
a single release, with nothing to say it had happened. Recorded here because
the bump will look like an unrelated chore when it comes.

---

## 0600 is right for files the app owns, and wrong for files another service reads

Tightening permissions after the plaintext-key finding broke a service.

`/etc/kea/kea-api-password` was written with `tee`, which made it root-owned,
and then `chmod 600`. Kea's Control Agent runs as `_kea`, so it could not read
its own password file and failed to start with *Permission denied*. The
correct target there is **0640 owned by the service user** — not 0600.

The two rules are not in tension once the question is asked properly:

* **A file the app owns and only the app reads** — `data/key.key`,
  `user_settings.json`, `jenkins_checks.json`, `.env` — is `0600`. Nobody else
  has any business reading it, and group access is pure exposure.
* **A file one service writes and another reads** is a handoff, and its mode
  has to name the reader. `0600` there does not protect the secret, it
  withholds it from the process that needs it.

The failure is instructive because it is the exact counterpart of the evening's
other lesson. Loose permissions are invisible until someone looks; tight
permissions on the wrong file fail loudly and immediately. **The loud failure
is the safer one**, which is an argument for tightening first and relaxing to
the measured requirement, rather than the reverse.

### Measured: the program does not currently do this anywhere

Worth checking rather than warning about in the abstract.
`scripts/nmas-oxidized-cred` is the one place NMAS writes a file another
service reads — Oxidized's `router.db`, `0600 oxidized:oxidized`. It does not
impose a mode. It stats the original, writes a temp file, then
`os.chmod(tmp, stat.S_IMODE(st.st_mode))` and `os.chown(tmp, st.st_uid,
st.st_gid)` before `os.replace()`. **It preserves the reader's ownership and
mode rather than asserting its own**, which is the correct shape and was
arrived at for a different reason (an atomic replace that cannot leave a
half-written credential file).

`config.open_secure()`, added the same evening, is `0600` and is used only for
files the app owns. The distinction holds, and now it is written down rather
than being a property nobody had articulated.

---

## A trailing newline is part of the password

The Kea rotation returned 401 against a password that was correct.

The password file had a trailing newline. **Kea includes it in the password;
`curl`'s `$(...)` strips it.** So the service and the test were comparing two
strings that differed by one byte, and the symptom — an authentication
failure — is indistinguishable from having simply got the password wrong. The
natural next move is to re-enter the password, which does not help, because
the difference is not in what was typed.

The rule, for anything in this program that ever writes a credential to a file
another service reads: **write it with no trailing newline, and say so at the
write site.** A comment is warranted because the absence of a newline looks
like an oversight to the next reader, and "helpfully" adding one breaks
authentication in a way that points at the wrong cause.

### Measured: covered, for the one path that exists

`nmas-oxidized-cred` refuses a username or password containing a newline
outright:

```python
if any(":" in v or "\n" in v for v in (username, password)):
    _fail("username and password must not contain ':' or a newline — "
          "router.db is colon-delimited and one would split the row")
```

The stated reason is the colon-delimited row format, not authentication — but
the check is the right one either way, and it is a refusal rather than a
silent strip. Silently stripping would be worse: the stored credential would
then differ from the one the operator supplied, with nothing saying so.

This is the same family as the ASCII guard. An em dash consumed by IOS and a
trailing newline consumed by Kea are both **one byte of invisible difference
between what was written and what was meant**, surfacing as a failure that
names something else entirely.

---

## Four weeks of failing, rendered as green

The largest silent failure in the project, found on 2026-09-23.

The background agent's last recorded run was **2026-08-28 23:26**. Trigger
`missing_golden_configs`, `tool_call_count` **0**, and the error:

```
anthropic-workspace-id is required when authenticating with an
identity-linked API key; send the id of the workspace this request acts in
```

So for four weeks it woke on schedule, decided there was work to do, and
failed at the **first API call** — before any tool ran, every time, with the
same rejection.

Three layers each did their part to hide it:

* **The record was a file nothing read.** `data/agent_activity.json` is
  written by `_append_activity()` and served by `/ai/agent_log`, but the only
  reader is the Agent tab, which nobody had reason to open.
* **The log line scanned like a success.**
  `log.info("agent_runner: done [%s] tools=%d success=%s cost=$%.4f", …)` —
  INFO level, the word *done* first, and the failure carried as `success=False`
  inside the format string. Twenty-six of those in a journal do not look like
  an outage.
* **The badge said "Active", in green.** The status logic had four states —
  running, paused, idle-user-active, active — and **no state for broken**.
  Whatever had happened on the last run, a scheduler that was neither paused
  nor mid-task rendered green.

None of the three is wrong on its own. Together they made a dead component
indistinguishable from a quiet one.

### The general rule this is an instance of

The project already had it written down, for a different subsystem: an empty
post-commit hook registry on a list that has a remote is an **error** and
records `last_push_failure`, because *"a commit that could have been published
and was not" must never be silent*.

The agent is the same shape and was missed because it is a component rather
than an operation. The fix is the same: `failure_health()` computes the streak
from the activity log, `get_status()` carries it, a failed run logs at
**ERROR** naming the error and the streak, the badge turns red with the count,
the **tab** badge shows it so it is visible without opening the tab, and a
banner names the error.

**`same_error` is the load-bearing field.** One failure is an incident; twelve
identical ones is a configuration problem that will not fix itself, and the
two deserve different words. A count alone would have read as flakiness.

### Two things it also revealed

**The trigger was stale.** `missing_golden_configs` came from the event
monitor's legacy enumeration — the Stage 3.3 finding — so the devices it named
as missing a golden config **had** one, in `config_repo/`. The agent's first
act on recovery would have been to create goldens for nine devices that
already had them. Fixed by 3.3a rather than by this work, and now pinned by a
test, because it is the trigger that fires first when the agent comes back.

**The fix might have been accidental.** Rotating the Anthropic API key an hour
earlier created it *in a workspace*, which may satisfy the very requirement
that had been failing. So a month-dormant component, holding a month-old tool
library, was one trigger away from waking against a system rebuilt underneath
it. `background_agent_enabled` was set to false before that could happen — the
persistent switch, checked at call time on every path, not the in-memory pause
that does not survive a restart.

That is the part worth keeping: **the repair arrived before the diagnosis**,
and only because someone went looking did the order come out right.

### A footnote on who wrote the switch

`background_agent_enabled` read `True` **explicitly** in the settings file —
the only key found written without anyone deciding. Measured across the whole
history: no template has ever sent it, no `set_user_setting` call has ever
named it, and `migrate()` cannot have seeded it. The server side was added in
`6a88a71` (2026-04-25) with a GET that reports it and a POST that accepts it,
**and no control anywhere**. So the code cannot have written it on its own; it
arrived in a request that carried it. A setting born reachable by `curl` and
invisible in the browser is a setting whose provenance nobody can reconstruct.

---

## A security test that failed one run in seventy

Found while re-running the suite after the agent work.
`test_the_ciphertext_is_not_the_plaintext` asserts that the break-glass
plaintext does not appear in the ciphertext, over four needles — including
`b"r1"`, a **two-byte** hostname.

Measured over 2000 sealings of the real fixture: the ciphertext is 953 bytes,
and `b"r1"` appeared in **1.40%** of them, against **1.45%** predicted by
chance (953 / 65536). The other three needles, all four bytes or more,
appeared in none.

So the test failed roughly one run in seventy, at random, in the file about
recovering from a lockout — and the failure meant nothing.

**A security test that fails at random teaches you to ignore security test
failures**, which is worse than not having the test. The needles are now
required to be at least four bytes (one chance in five million per run), the
short ones are excluded deliberately, and a second test pins that exclusion so
the hostname is not helpfully added back by someone who notices it is missing.

It is `redact.py`'s 8-character value floor arrived at from the opposite
direction: there a short value matches everywhere and corrupts the line; here
a short value matches by accident and cries wolf. Same cause — a needle
shorter than its haystack's noise — and the same remedy.

---

## Per-platform branches accumulate decisions and lose the record of them

Twice in one evening, the two platform branches of
`modules/nsot/bootstrap_config.py` differed with **nothing in the code saying
why**:

* **Key generation.** `cisco_ios` emits `crypto key generate rsa modulus
  2048`; `cisco_iosxe` emits nothing. That one turned out to be deliberate
  and load-bearing — vrnetlab generates the key itself on the C8000v, and
  emitting it there would regenerate a key the device is mid-way through
  using. The reason was recorded, in `ssh_key_lines()`. Good.
* **`transport input`.** `cisco_ios` emitted `ssh`; `cisco_iosxe` emitted
  `all`, which includes telnet. **Nothing said why**, and the answer was that
  nobody had decided: each branch had faithfully reproduced its own reference
  device (`s1.cfg` emits `transport input telnet ssh`, `r1.cfg` emits
  `transport input all`), and the vIOS branch happened to have been tightened
  further at some point while the C8000v branch had not.

So one divergence was a decision with a reason attached, and the other was
two independent inheritances that had never been compared to each other.
**From the outside they are indistinguishable** — both are a difference
between two branches of the same function.

That is the pattern worth naming. A per-platform branch is where
platform-specific truth *should* live, which makes it also the place where an
un-decided difference is least likely to be questioned: the reader's first
assumption is that the platforms differ because platforms differ.

The remedy is not fewer branches. It is that **a difference between branches
carries its reason at the emit site**, so the next reader can tell a decision
from an inheritance without reconstructing the history. `ssh_key_lines()`
already did this; the `transport input` line now does too, including the
explicit note that the standing "reproduce what predates it" rule does *not*
apply to a bootstrap config, because a device that does not exist yet has no
behaviour to preserve.

### And a measurement record is not a template

Changing the generator broke `test_the_c8000v_shape_matches_bp_c8k`, which
asserts the probe fixture and the generator agree. The obvious fix — edit the
fixture — would have been wrong: `bp-c8k.cfg` is **what a real C8000v
actually booted in stage A**, and the probe fixtures exist so those
measurements stay readable.

So the divergence is *declared* rather than erased: one `(booted, generated)`
pair, named, with the test still comparing every other line. And it fails if
the divergence **disappears** as well as if a new one appears — a
disappearance means somebody tidied the fixture, which is the thing worth
protecting against. Same shape as the seed declaration and the unreachable
allowlist: a list that must not grow silently, and here also one that must
not silently shrink.

---

## A guard ages against its own payload

`GET /ai/agent_log?limit=2` returned:

```json
{"entries": [], "error": "AI is disabled", "status": {}}
```

So switching the agent off **suppressed the twenty-six recorded failures and
the workspace-id error that were the reason for switching it off**. The
health surface built specifically so a dead component could not look quiet
went silent exactly when its history mattered most. An operator finding it
disabled next month would have learned nothing — not even that it had ever
failed.

The route was not carelessly written, and that is the interesting part.

**When it was written it returned only a log.** For a log, "AI is disabled"
plausibly does mean "nothing to say", and a 503 with that message is a
reasonable thing to write. Then `status` gained `health`, and the route
started carrying something the guard had never been asked about. Nobody
revisited it, because nothing about adding a field to a payload suggests
re-reading the guard above it.

So the rule is not "don't short-circuit". It is that **a guard is written
against a payload, and it stops being correct when the payload grows.** That
is not visible at the guard — it is visible at the moment the payload
changes, which is the moment nobody is looking at the guard.

### A read reports; an action refuses

The correction is a distinction, not a removal. Surveyed across `app.py` and
every blueprint: **18 routes short-circuit on a disabled or unconfigured
state. Fifteen are actions** — `/ai/agent_run`, `/ai/agent_pause`, the NetBox
imports, the Jenkins job creation — and refusing is exactly right there. A
disabled agent must not be made to act, and loosening that would be the
opposite mistake.

Of the three GETs, only `/ai/agent_log` was withholding. `/drift/settings`
already reports its state as data. `/monitoring/stack/<name>` already returns
`ok: true` with an unconfigured tool named, under a comment saying *"Not an
error. An unconfigured tool is a decision, and showing it in red teaches the
operator to ignore red."* `/topology_view/svg` refuses, correctly: there is
no SVG without a configured service, no accumulated history being hidden, and
the refusal names the setting to change.

The monitoring cards got it right because they were **designed** around the
question. `/ai/agent_log` got it wrong because its guard predated the
question being asked.

### Is it testable the way unreachability is? No — and the reason matters

Reachability tests cannot catch this, and neither can coverage:

* The route **is** reachable, and a per-route reachability check passes.
* The branch **is** taken — that is the defect. Coverage marks it green.
* The failure is a *behavioural* property of a reachable, covered route:
  under a particular state, it returns less than it knows.

What catches it is exercising the route **in the degraded state** and
asserting the payload still carries what the operator needs. That is
per-route work, because every subsystem has a different disable lever.

What generalises is the **classification**. `test_disabled_is_a_state.py`
walks the AST for every GET that names a disabled/unconfigured state in a
return, and requires each to be declared **`reports`** or **`fetches`**. A
new one fails the test until somebody decides which it is. The list must not
grow silently, and — caught by its own ghost check on the first run, when it
still listed the two routes this work had just fixed — it must not keep
entries for routes that no longer short-circuit either.

A scan cannot know that an SVG legitimately has nothing to return while an
activity log does. A person can, once, and the list records that they did.

---

## The agent has never made a tool call

Counted across the whole activity log: **27 runs, `tool_call_count` zero in
every one.** Twenty-six failures, and one entry recorded as a success —
2026-08-28 23:26:27, no tools, no summary, no errors, five minutes after the
previous failure.

So the health surface added earlier was reading correctly and **the data was
wrong**. A backward streak stops at the last success, and that entry was one,
so the badge showed nothing even after the route was fixed to report it.

### What that "success" actually was

Diagnosed rather than guessed. `run_background_task` has two ways to leave
the event loop early:

```python
if _user_is_active():
    stop_session(session_id)
    log.info("... interrupting task %s — user became active", session_id)
    break                       # <- appends nothing

elif etype == "interrupted":
    errors.append("Task was interrupted.")
    break                       # <- appends
```

**One exit path recorded and the other did not.** A task interrupted because
the operator opened the browser left `errors` empty, and
`success = not bool(errors)` made it the only time the agent has ever
"worked".

The asymmetry is the whole defect, and it is invisible at either site: each
`break` is locally reasonable, and the difference only means something at the
line that computes `success` from `errors`, forty lines away.

### "No exception reached the top" is not success

`success` was a fact about the interpreter, not about the network. A run
records an `outcome` now — `ok`, `failed`, `interrupted`, `inconclusive` —
each with a reason, and `success` derives from it. A run with no tool calls
and no output is **inconclusive**: nothing observable happened, which is a
different claim from either "it worked" or "it broke".

The streak counts back to the last run that actually **worked**. An
interrupted or inconclusive run neither ends it — it is not evidence the
agent works — nor inflates the failure count, because it is not a failure.
Two facts, two numbers: `consecutive_failures` and `runs_since_ok`.

Historical entries have no `outcome` field and are classified from what they
carry. An old entry **cannot** say it was interrupted, because nothing
recorded that, so it lands in `inconclusive`. The diagnosis above belongs in
this document, not retroactively in the data: rewriting a record to match a
later diagnosis is how a record stops being evidence.

### What it means for Stage 8

**Nothing in the tool library has ever executed in production.**

Stage 8.2 was written as "check the 73 tools against what the program has
become". It is not that. It is **their first run**, on a library written
against an architecture that has since been rebuilt underneath it. Every
"correct" verdict in that review is a prediction rather than an observation
and should be written as one — and 8.4's "observe one real run" stops being a
final confirmation and becomes the only evidence the review ever produces.

It also reframes the four-week outage. The agent did not stop working; **as
far as its own record goes, it has never worked.** The failures are the
visible part of a component that has produced no observable effect in its
entire history — which is the strongest possible argument for the Stage 8
ordering: fix the library, gate the authority, and only then let it run.

---

## Three guards, three fixes, and the screen still said nothing

The same data was hidden three times in one feature, and **every test passed
at each stage**:

1. **The route.** `GET /ai/agent_log` returned `{"entries": [], "status": {}}`
   with a 503 when AI was off. Fixed — and the endpoint then demonstrably
   carried 26 failures and the workspace-id rejection.
2. **The success flag.** `success` meant "no exception reached the top", so a
   no-op run ended the failure streak. Fixed — and the streak then read 26.
3. **The client.** `loadAgentTab` had its own
   `if (window._aiEnabled === false) { … return; }`, so the page rendered
   *"AI is disabled — enable it in Settings"* with no count, over an endpoint
   that was returning everything.

Each fix was correct and each was verified. **The boundary kept being drawn
above the last remaining guard.** A test that asserts the endpoint carries
the data cannot see a client that refuses to draw it; a test that greps a
template for a string cannot see a branch that returns before reaching it.

That is the lesson, and it is not "write more tests". It is that **a test
asserts something about a layer, and the defect was always in the next layer
out.** Each round the evidence was real and the conclusion — "fixed" — was
wrong, because the thing being measured was never the screen.

### So the test moved to the screen

`agentHealthBanner` and `agentBadgeState` are now pure: no DOM, no network.
`test_agent_panel_renders.py` lifts them **out of the rendered page**, not a
copy, and executes them in duktape against the exact health block the
deployed endpoint returned.

That was still not enough, and the negative control said so. **Reinstating
the client guard left nineteen of twenty tests passing**, because the pure
functions sit *below* it — the same mistake, one layer down, made while
fixing it. So `TestLoadAgentTabItself` executes `loadAgentTab` itself against
a stub DOM and a stub `fetch`, and reads what lands in the elements. It is
the only assertion in the file that spans the guard, and reinstating the
guard fails four of its tests.

Duktape parses `async` and has no event loop, so an async function returns a
promise whose body never continues past the first `await` — measured, every
element came back empty. The test strips the asynchrony **and only that**:
`await X` becomes `X`, no branch is touched, and it asserts the strip applied
so a silent no-op cannot make the class vacuous.

### The sweep

Client loaders that return early on a disabled or unconfigured state:

| Loader | Verdict |
|---|---|
| `loadAgentTab` | **was hiding** — fixed |
| `loadAgentTimers` | **was blanking its panel** — fixed; a schedule you cannot see is one you cannot check |
| `loadRemotePanel` | correct — *"No remote for this list. Its history is on this host only."* |
| `topoSvcRefresh` | correct — names the setting to change |
| `_stackRender` | correct — shows the tool's own message; designed around the question |
| `base.html` `setInterval` | correct — an auto-troubleshoot **action**, rightly skipped |

The monitoring cards were right because somebody asked the question when
writing them. Everything written before the question was asked is where the
answers differ, which is exactly what made them worth sweeping for.

### And the grep bit me one more time

The first version of the test asserting `loadAgentTimers` no longer blanks
its panel searched the function body for `panel.innerHTML = ''` — **and the
comment explaining the fix quotes that exact code.** The test failed against
correct code, for the third form this project has now seen of *prose about
code is not code*: a test matching a docstring, a checker matching a
docstring, and now a test matching its own explanatory comment. It asserts on
the assignment statement instead.

---

## A set difference passes vacuously, and that is a tell

Sixth instance of the can't-fail control, and the first with a **reliable
tell** rather than a story.

The census test:

```python
used = set(re.findall(r'"((?:dcim|ipam)/[a-z-]+/)"', src))
missing = sorted(used - known)
assert not missing
```

It passed immediately, which for a first run is the signal. `used - known` is
empty when `used` is empty, so **a regex that matched nothing makes the
assertion true** — and there is no difference at all between "every endpoint
is counted" and "the scan found no endpoints".

That is the general shape, and it is worth stating as a rule rather than as
six anecdotes:

> **An assertion over a set difference passes vacuously when either set is
> empty. It needs a floor on its inputs.**

`assert not (A - B)` proves something only once you know `A` is non-empty.
The floor does not have to be exact — `assert len(used) >= 12` against a
measured 15 is enough, because the failure it guards against is the regex
matching *nothing*, not the regex matching fourteen.

The same reasoning covers the whole family:

* `assert all(...)` over an empty iterable is `True`;
* `assert not [x for x in xs if bad(x)]` is `True` when `xs` is empty;
* `assert expected.issubset(found)` is `True` when `expected` is empty — the
  direction matters, and it is the one people get backwards;
* a scan for offenders that finds none **and** a scan that could not run
  produce the same empty list.

`test_blueprint_reachability.py` and `test_disabled_is_a_state.py` already
carry a `_the_scan_finds_something` test for exactly this reason. What was
missing was the statement that the two are the same rule, so the third
occurrence does not have to be rediscovered as a fresh surprise.

### The other five, for the record

1. `LAUNCH_SKIP_MARKER in text` — a substring, satisfied by
   `..._startupX`, and a presence check inside the function written to
   replace presence checks.
2. `sshpass … || echo PASS` — passed on a KEX failure, so it would have
   passed with the device powered off.
3. `--dry-run` returning before the persist chain — the control could not
   reach the code it was controlling.
4. `'"next_ts"' not in ast.unparse(...)` — `ast.unparse` emits single quotes.
5. `os.utime` on the repo copy while the code read the legacy copy's mtime.
6. This one.

Four of the six are the same underlying fault: **the check and the property
were about different objects.** The set-difference form is the first that is
about the right object and still cannot fail, which is why it is worth its
own rule.

---

## Two platform namespaces, and a gate that silently opened

Building the wizard's platform list, `/onboard/platforms` iterated
`platform_map`'s keys and looked each one up in
`BLOCKED_PENDING_MEASUREMENT`. Every platform came back **unblocked** —
including `cisco_ios`, the one stage D exists to block.

`platform_map` is keyed on **NetBox platform slugs**: `cisco-ios`,
`cisco-ios-xe`. `bootstrap_config`, the parsers and the template directories
are keyed on the **config dialect**: `cisco_ios`, `cisco_iosxe`. Hyphens and
underscores, and `ios-xe` against `iosxe`.

`modules/nsot/platform.py` already owns the translation — `_FROM_NETBOX_SLUG`,
reached through `platform_for_device()`, with a docstring explaining that
`device_type` is a Netmiko driver and not a dialect and that conflating them
is how "change device_type to cisco_xe" came to alter transport. The mapping
was there; the new code simply did not use it.

**A dictionary lookup that misses returns the default**, and the default here
was "not blocked". So the failure mode was a **gate that silently opened** —
no error, no log line, a platform list that looked complete, and a refusal
that had been carefully written, tested and documented quietly not applying.

The fix is not a second mapping. It is calling the function that owns the
first one: a second copy is how the two come to disagree about what
`cisco-ios` means, and the disagreement would show up as exactly this again.

**It was caught by a test asserting the blocked platform is LISTED**, which
existed for an unrelated reason — an absent option teaches the operator the
tool does not support their device. The test for the refusal itself
(`test_a_vios_target_is_refused` in 4C.1) passed throughout, because it calls
`build_plan` with the dialect directly. The unit was right and the wiring was
wrong, which is the seam this project keeps finding.

---

## Prose about code is not code: the fourth form, and a reliable tell

Three forms were already recorded: a **test** matching a docstring, a
**checker** matching a docstring, and a **test matching its own explanatory
comment**. The fourth arrived in the same session as the third:

```python
assert src.index('onclick="openOnboardWizard()"') < src.index("{% if devices %}")
```

The button *is* before the guard. The test failed anyway, because the comment
explaining that decision **quotes the tag**:

```
{# … Deliberately OUTSIDE the `{% if devices %}` block below … #}
```

So the search found the comment, six lines above the button, and concluded
the button came after it.

By now the tell is reliable enough to state as a rule alongside the
set-difference one:

> **A pattern that can appear in English needs an anchor.** Match a code
> construct at the start of a line, or parse it — never as a bare substring
> of a file that also contains prose about that construct.

The anchored version (`re.search(r"^\s*\{% if devices %\}", src, re.M)`)
cannot match inside a comment, because the comment's copy is not at the start
of a line. Every one of the four instances would have been prevented by
either that rule or by parsing instead of grepping, which is what
`check_removed_definitions.py` and `tests/astcheck.py` now do.

The reason it keeps happening is worth naming: **the better the comment, the
more likely it quotes the code it explains** — and a good comment is
precisely what a careful author writes next to a subtle decision. So the
places most likely to carry an explanatory quotation are the places most
likely to have a test asserting something subtle.

---

## A positive assertion found what every negative-space test missed

The slug/dialect gate — `/onboard/platforms` reporting every platform
unblocked, including the one stage D blocks — was caught by a test asserting
**"the blocked platform IS LISTED"**, written for an entirely unrelated
reason: an absent option teaches the operator the tool does not support their
device, which is a different and wrong lesson.

Everything written to catch the *problem* passed:

* `test_a_vios_target_is_refused` (4C.1) — passed, because it calls
  `build_plan` with the dialect directly. The unit was right.
* the blueprint reachability check — passed.
* the removed-definition check — passed.
* every "no offenders" scan in the suite — passed.

**A gate that silently opens produces no offenders.** That is the whole
problem with it: there is nothing to find. A dict lookup that misses returns
the default, the default was "allowed", and the absence of a refusal looks
exactly like the absence of a reason to refuse.

The test that caught it was the only one asserting a **specific, expected,
positive fact**: *there should be at least one blocked platform in this list,
and it should carry a reason.* An empty list would have satisfied every
negative-space assertion in the file and failed that one immediately.

### The same family as the set-difference rule

Both are instances of one thing:

> **A suite of "nothing is wrong" assertions cannot distinguish a healthy
> system from an absent one. It needs at least one assertion about something
> concrete it expects to be true.**

`assert not (A - B)` passes when `A` is empty. `assert not offenders` passes
when the scan found nothing *and* when the scan could not run. `assert no
platform is wrongly unblocked` passes when there are no platforms.

The floor-on-inputs rule is the mechanical form of it — check `A` is
non-empty first. The broader form is the design instruction: **every scan
needs a companion that names something it expects to find.** In this codebase
that has become a pattern with a name, `_the_scan_finds_something`, in
`test_blueprint_reachability.py`, `test_disabled_is_a_state.py`,
`test_netbox_census.py` and now `test_platform_keying.py` — but those are
floors on the scan, not assertions about a specific expected fact, and this
case needed the stronger form.

It is also an argument for writing tests that assert what the feature *is
for*, not only what must not happen. The one that caught this was about the
operator's experience — "a blocked platform must still appear, so they learn
it is blocked rather than unsupported" — and it happened to be the only thing
in the suite that required a blocked platform to exist at all.

---

## Why there is no PlatformRef

`ListRef` (Stage 1.7) exists because a device list's **name** and its **slug**
are both stored, both compared, and either can arrive from a caller — so the
pair became a type with `matches()`, and the comparison stopped being a
convention.

A platform looks like the same shape and is not. There are three namespaces:

| namespace | example | where it lives |
|---|---|---|
| **dialect** | `cisco_iosxe` | **stored** — the manifest, the parsers, template dirs, `bootstrap_config` |
| NetBox slug | `cisco-ios-xe` | an **input** — `platform_map` keys, NetBox |
| Netmiko driver | `cisco_xe` | an **input** — `device_type`, and it overlaps the dialect on `cisco_ios` |

**Only one form is ever stored or compared.** `inventory_index()` calls
`platform_for_device()` and the manifest records the dialect; nothing compares
a slug against a dialect, because nothing keeps a slug. That is a
*translation* problem, not an identity one, and a `PlatformRef` would be
carrying a second value that has no consumer.

So the intervention matches the failure instead. The failure was **an input
format reaching a table keyed on the canonical one, where the miss returned a
permissive default** — answered by `platform.assert_dialect()`, which refuses
at the boundary and names `platform_for_device()` in the message.

Two supporting findings while measuring this:

* **`manifest.py`'s docstring example showed `"platform": "cisco-ios-xe"`** —
  a slug, where the code stores a dialect. The example taught the wrong
  namespace to anyone who read it, which is one way a new caller acquires the
  belief that led here. Corrected.
* **`build_plan()` resolved the repo path before validating its inputs**, and
  `get_list_data_dir()` calls `os.makedirs()` — so a refused plan created a
  list directory for a device that was never onboarded. Caught by the
  `conftest` data-directory guard the moment the refusal test ran, which is
  the guard finding a real ordering defect rather than test residue.

`test_platform_keying.py` records which keying each of the eighteen files
carrying a platform literal means, because three namespaces that overlap on
`cisco_ios` cannot be told apart from the value. A file that grows a literal
and is not declared fails; a declaration for a file that no longer has one
fails too.

---

## "That closes every build step" — true of the list, false of the system

Six steps were planned for Stage 4C, six were built, each with tests and
negative controls, and the commit closing the last one said *"that closes the
4C build steps."* It was accurate about the list and wrong about the system:
**`run_onboarding()` had no caller outside tests, `/onboard/create` returned
501, and the four step adapters did not exist.**

The operator read that sentence, got ready to sit at the machine for the
probe, and asked for the runbook. A runbook written that day would have
dead-ended one step after their stop point — a node booted, a temporary list
created, and the teardown that has never run still not exercised.

### The same shape as the gate, one layer up

This stage produced two of them:

* **The slug/dialect gate.** `BLOCKED_PENDING_MEASUREMENT` was correct,
  tested, and documented. `/onboard/platforms` looked NetBox slugs up in it,
  missed, and reported every platform unblocked. The unit was right and the
  wiring was wrong.
* **This.** Six units right; the wiring absent entirely.

**The tell is identical: every test that passed sat below the missing
connection.** `test_onboard_ordering.py` proved the ordering contract holds —
for injected steps. `test_onboard_plan.py` proved refusals work — called
directly. Nothing asserted that anything *calls* them, because the thing that
would have was the probe, and the probe was the last step.

It is the third form of the boundary problem recorded this week, after the
agent panel's three guards and the drift panel's inline renderer. The lesson
each time: **a test asserts something about a layer, and the defect lives in
the joint above it.**

### What 4C.7 changed, and what it could not

`real_steps()` assembles the four production adapters, `create` calls
`run_onboarding` with them, and `test_onboard_ordering.py` gained a class
that runs the **shipped adapters** against faked *dependencies* rather than
faked steps — so the seam moved from above the adapters to below them. The
first thing it caught was a real trap: `sync_list_to_netbox` **returns**
`{"blocked": True}` when writes are off rather than raising, and
`run_onboarding` reads a return as success. A blocked write would have
carried the run into the commit.

What no test arrangement fixes is the ordering mistake: **the assembly was
never on the list.** The six steps were the pieces, and "assemble them" was a
seventh nobody wrote down — which is why the closing sentence was possible to
write in good faith.

### And a negative control found the same shape inside the fix

4C.7 added the write-gate precondition at plan time, so `netbox_allow_writes`
being off is a blocking reason named on the review screen rather than a raise
mid-run. Running the control — remove the precondition — changed **nothing**:
27 tests passed either way.

The check was written, correct, and **exercised by nothing**. Present,
plausible, and proving nothing, which is the slug/dialect gate again inside
the commit that was fixing it. Six tests now cover it, including the one that
matters: with writes off and a NetBox plan, the reason reaches
`summary["blocking_reasons"]`, which is what the review screen renders.

---

## A blueprint's full path appears nowhere in its source

Two paths in the Stage 4C runbook — `/settings/integrations` and
`/netbox/safety/remove/preview|apply` — were checked by grepping the source
and reported missing. **Both exist.** The decorator says:

```python
bp = Blueprint("netbox_safety", __name__, url_prefix="/netbox/safety")
...
@bp.route("/remove/preview", methods=["POST"])
```

The full path is assembled **at registration**, so the string
`/netbox/safety/remove/preview` occurs in no file. A grep for it cannot
succeed, however correct the route is, and `grep` returning nothing is not
evidence of absence — it is evidence the string is not in a file.

`app.url_map` is the only authority, which is what `scripts/nmas-verify-runbook`
consults. It walks a runbook for `curl … localhost:5000/…` commands and
resolves each against the real map, method included.

This is the same family as the slug/dialect gate and the census's
set-difference: **a lookup that misses tells you nothing about the thing you
were looking for.** A dict `.get()` returns the default, a grep returns
nothing, and both read as a fact about the system when they are facts about
the query.

### What it cost, and what it would have cost

It cost one exchange. It would have cost a sitting: the operator would have
booted a C8000v, created a temporary list, reached step 12 — the acceptance
for the whole probe — and found the teardown pointing at a URL they had
already been told did not exist.

So **step −1 exists to make a wrong path cost a grep rather than a sitting**,
and it runs before anything is created. It is the cheapest step in the
runbook and the only one that protects the other fourteen.

### And it found a real one

Verifying the paths meant reading the routes, which turned up a defect the
grep question had hidden: **`/netbox/safety/remove/apply` requires a one-shot
token issued by the preview.** `_authorize()` checks the master switch,
consumes the token, and **recomputes the plan**, refusing if it changed. The
runbook's apply sent only `list_name` and would have been refused with
*"Missing confirmation. Run the preview again."*

That is the third inferred-signature finding in this stage — after
`template_for_platform` / `get_device_by_name` and `rotate()` — and the first
found by someone else asking. The pattern across all three: **the shape I
assumed was the simpler one**, and the real one had a guard in it.

---

## Step 1: the name/slug split reappears where no type can catch it

Running step 1 produced two corrections, both about the same thing: **the
runbook is code that nothing type-checks.**

### `nmas-probe` is not `nmas_probe`

`config.list_slug()` replaces every non-word character with an underscore, so
the list created as `nmas-probe` lives in `data/lists/nmas_probe/`. Steps 8
and 10 and the credential-recovery command all used the **name** as a path
and pointed at a directory that does not exist, while every API call in the
same runbook correctly used the name.

This is exactly what `ListRef` was built for in Stage 1.7 — its docstring
says so: *"`name` is what the operator sees. `slug` is the directory. They
are different strings and comparing one to the other is always false, which
is the bug this type exists to make unrepresentable."*

**Unrepresentable in Python. Perfectly representable in bash.** That is the
finding. The fourth instance of this shape in the project, and the first
outside the program:

1. the drift state file — a `next_ts` key written and read by nobody
2. the slug/dialect gate — an input format meeting a canonical-keyed table
3. the blueprint-prefix grep — a route's full path present in no file
4. **this** — a name where a slug belongs, in a document

The first three were answered with types, tests or checkers. There is no
equivalent for a runbook, so the answer is the table at the top of
`STAGE4C_PROBE.md`: *these commands use the name, those use the slug.*
Stating it is weaker than enforcing it, and it is what is available.

### The directory does not exist yet, and that is correct

Step 1's acceptance was `ls -la data/lists/ | grep nmas-probe` — wrong twice
over. `get_list_data_dir()` calls `os.makedirs()` **on first write**, so a
freshly created list has no directory at all. The registration lives in
`data/device_lists.json` and shows up in `GET /device_lists` with
`device_count: 0`, which is the thing that actually happened.

Worth recording because that same laziness was a **real defect** two steps
earlier in this stage: `build_plan()` resolved the repo path before
validating its inputs, so a plan that was *refused* still created a list
directory for a device that was never onboarded. The conftest guard caught
it. Here the laziness is the correct behaviour and the assertion was wrong —
the same mechanism, read correctly once and incorrectly once.

**Both corrections came from running the step.** Step −1 verified every
endpoint and could not have caught either: one is a filesystem path and the
other is a claim about *when* a directory appears. A checker finds what it
was pointed at.

---

## Step 3: the third time the binds line was the difference

`nmas-onboard-c.clab.yml` shipped without a `binds:` entry. The node launched
*"with 1 SMP/VCPU"* on the stock vrnetlab script and sat at 112% CPU —
**grinding, not stalled**, which is the distinction that identified it: the
very first bootstrap probe failed this way and never completed in ~40
minutes. Diagnosed from the launch line rather than from the symptom.

Steps 0-2 stand. The node was destroyed and the probe network removed before
anything else was created, so the census baseline is still the baseline.

### Twice is a coincidence

1. The first bootstrap probe — stock script, one vCPU, no completion.
2. Stage B — the injected `username admin ... password admin`.
3. This.

Each fix was a line somebody had to **know** to write, in a file nothing
checks. The rule is mechanical, so `test_probe_topologies.py` now asserts it:
every `cisco_c8000v` node under `docs/bootstrap-probe/` binds something over
`/launch.py`, from a **relative** path inside the probe's own directory.

### The half a probe cannot show you

The patch does two things, and they fail in opposite directions:

| | how it fails | what you learn |
|---|---|---|
| `smp="2"` | loudly — no `Startup complete` | after ~40 minutes |
| the user-skip | **silently — it succeeds** | nothing |

Without the skip the node boots, answers SSH, reports healthy, and holds
`admin`/`admin` while the generated config says otherwise. Inside the Stage
4C probe that is worse than a hang: **the probe would pass**, and what it
would have proven is that the wizard can onboard a C8000v onto a credential
nobody intended — the exact hazard stage 2 exists to prevent, reproduced
inside the wizard's first run.

This is the same shape as every silently-opening gate in this project. A
node short a vCPU is an offender that announces itself; a node short the
user-skip produces no offender at all.

### Why the copy, and why the name

The bind is staged from `~/labs/lab/patches/c8000v-launch.py` into the
probe's own `patches/`, because **a throwaway lab whose teardown can reach
into production is not throwaway**.

It is named `c8000v-launch-adopted.py`, not `c8000v-launch.py`, because that
name is already taken in that directory by the stage-A/B copy — which
predates the user-skip **on purpose**. That copy is what makes
`nmas-bootstrap-probe.clab.yml` reproduce the hazard stage B measured.
Writing the adopted script over it would have silently retired the probe
that measured the thing, while every file still parsed and every test still
passed.

### Negative control

The in-suite control drives `unpatched_c8000v_nodes()` against three
synthetic topologies: an unbound c8000v (caught), a c8000v bound over
`/opt/launch.py` instead of `/launch.py` (caught — the near miss a reader
would assume was covered), and an unbound vIOS (correctly not an offender,
since nothing is injected ahead of its startup config and it boots on one
vCPU).

Separately, the real file was reverted to its as-shipped form in a temp
directory and run through the same function: `['nmas-onboard-c.clab.yml:bp-onboard-c']`.
**The check was shown failing against the artifact that actually failed**,
not only against a fixture written to fail.

---

## The harness that could not tell "passed" from "never ran"

For most of 4C.8 there was no pytest on the machine doing the work: no
pytest, no pip, no ensurepip, no network. So the test bodies were executed
through a hand-rolled driver instead -- and **every "N passed" reported in
this stage before tonight was harness-only.**

The substantive claims held when pytest finally ran. That is luck rather
than method, and the mechanism is worth stating exactly:

> The harness ran only `Test*` classes and fixtureless `test_*` functions,
> **silently skipped everything else**, and printed a pass count that could
> not distinguish *passed* from *never executed*.

That is the vacuous-pass failure, inside the tool built to hunt vacuous
passes. Every scan in this project now carries a `_the_scan_finds_something`
floor for exactly this reason, and the harness had no floor at all.

**The tell was visible and went unread.** `test_probe_topologies.py`
reported **0 passed** under the class-based driver and **4** under the
function-based one -- the same file, the same moment, two different answers.
That was noted and moved past as a quirk of the driver. It was the driver
announcing it could not see half its input.

### What the real run found

2,638 passed, 6 failed, first genuine run of this suite anywhere:

| failure | what it was |
|---|---|
| `test_no_ip_literals` x2 | real -- this lab's addresses in 4C.8 docstrings |
| `test_onboard_plan` x2 | real -- and in the file flagged as unverifiable |
| `test_portability` | **residue**, not a regression: a `C:/TFTP-Root` dated to the original deployment, created by the pre-Phase-0 import-time `makedirs` |
| `test_inline_javascript` | **the checker was wrong**, see below |

The portability one is the sharpest: the assertion is *"no such directory
exists"*, and a month-old artefact satisfies its negation as truly as a
fresh one. The test is right to fail and the fix is deleting the directory,
not softening the test. It also means **this suite had never been run on a
machine carrying traces of the old behaviour** -- coverage inherited, not
designed, the same shape as the drift checker's nine devices.

---

## Two checks of one property, and the older one was wrong

`test_inline_javascript.py` held two parsers of the same thing:

* `TestNodeParsesEveryInlineScript` -- `node --check` over **raw templates**;
* `TestEveryInlineScriptParses` -- dukpy over the **rendered page**.

The dukpy one was added later, and its docstring says precisely why it
renders first:

> A template is not JavaScript. `window.applyAiEnabled({{ ai_enabled |
> tojson }})` is valid Jinja and, read as JS, is an object literal with an
> invalid property name -- so parsing the raw file reports a defect in
> correct code.

The reason was written down, and the older check was left in place holding
the opposite behaviour. It stayed green only because **node was installed on
neither machine**, so it skipped. Installing node to run this suite turned
it on for the first time, and it failed on the two blocks its sibling's
docstring had named in advance:

    base.html:885    window.applyAiEnabled({{ ai_enabled | tojson }});
    index.html:6628  the same line

Both correct. Both working in the browser. **A checker that reports a defect
in correct code is one that gets removed or routed around** -- which is the
literal argument used when the dukpy version was written, arriving as an
actual event.

### The failure report omitted the failure

The node check printed `stderr.strip().splitlines()[-1]`. On node 18 the
last line of a syntax error is the version banner, so a genuine parse
failure reported:

    Node.js v18.19.1

and named nothing -- no file, no line, no token. A report that omits the
failure is worse than no report: it costs a diagnosis *and* looks like one.
The replacement takes the first line containing `Error`.

### The fix: one input, several parsers

Merged rather than corrected in place. Two checks of one property will
diverge again; what differed here was not the parser but **what it was
pointed at**, so that is what became singular:

* `parsers()` returns every parser available -- dukpy always, node when
  `shutil.which("node")` finds it. node is not required, and when present it
  is used rather than skipped, because it is the stronger parser.
* Both wrap the block identically (`_WRAPPER`), so they are at least asked
  the same question about top-level `return` and `await`.
* Both parse the **rendered** page.

Three controls guard the merge:

1. **`parsers()` is non-empty and names dukpy** -- an empty list would make
   every check vacuously true and look exactly like a clean run.
2. **Every parser rejects `await` without `async`, individually.** `_parses`
   returns on the first failure, so an aggregate control proves the first
   parser works and says nothing about the second: node being installed has
   to mean node is checking something.
3. **The raw Jinja form must fail to parse and the rendered form must
   pass.** This is the reason the check renders, pinned as an assertion
   rather than left in prose -- prose about code is not code, and the prose
   was already there and was already ignored.

---

## Merging two of three is how the remaining copy becomes the defect

One list of form fields existed in three places:

1. `_plan_args()` in `routes/onboard.py` -- what the server reads;
2. `onboardFormPayload()` in the wizard -- what the client sends;
3. an array of element ids -- what the client **watches** for changes.

4C.8 added three fields. The first two were merged into single readers two
commits earlier, precisely to stop them drifting. **The third was not
touched, and it is the one that broke.**

```js
['obHostname', 'obPlatform', 'obMgmtIp', 'obMgmtIntf'].forEach(...)
```

The original four ids. So `obMgmtMask`, `obMgrIntf` and `obMgrGw` were
**read and sent correctly** and were watched by nothing. An operator filling
in the netmask saw *"no network mask"* sit there unchanged.

**Nothing was wrong with the payload**, which is what made it hard to see
from either end: reading the payload builder shows all seven fields, and
reading the binding list shows four ids that are all real. The defect exists
only in the relationship between them.

Worse than a straightforward failure, too. A wizard that looks broken while
working teaches the operator to stop trusting the panel -- and the panel is
the only thing standing between them and a commit.

**Found by the operator, on the live page, mid-probe.** Not by a test.

`ONBOARD_FIELDS` is now the one list, read by the payload builder and by the
binding loop. The general form is worth keeping:

> Merging two of three copies is not a partial fix. It concentrates the
> divergence in whichever copy was left.

---

## The target list: carried, never derived

The same operator nearly onboarded into `Default` five minutes earlier. It
was caught because the review screen names the list and they were reading at
a hard stop built for exactly that -- **a line that is correct about 95% of
the time, which nobody reads on an ordinary run.**

`_active_list()` fell back to `get_current_list_name()` when the request did
not name a list. That is the rule `PipelineContext.list_name` already
established the expensive way: the pipeline asked `get_current_list_name()`
at three points after the push, and a list switch during a 45-90s
convergence window committed one network's captures into another's
repository. **The wizard was on the wrong side of a rule this codebase
already had.**

### The asymmetry is what decides it

Onboarding into the wrong list leaves a **commit, a NetBox object and a
`devices.csv` row** in a live network. Repairing it means the
provenance-based Remove plus a git revert -- and Remove is the mechanism the
Stage 4C probe exists to prove, which is to say it has never run.

**The failure mode is repaired by a mechanism that is itself unproven.**
That is the argument for refusing rather than defaulting, and it is not
about convenience.

The list is also the one input that decides what every other input *means*:
the name collision is checked in that list's manifest, the credential comes
from that list's resolver, and the NetBox objects are recorded against that
list's slug. It was the only field inherited rather than stated.

`_target_list()` now raises `NoTargetList` rather than guessing; the wizard
sends it as an ordinary `ONBOARD_FIELDS` entry, so it re-validates like
everything else, and `/onboard/lists` populates the select on every open.

### Three findings from writing the tests

**`/onboard/create` answers 403, not 400** -- the identity gate runs before
input validation, so an unauthenticated caller is refused without the route
parsing their payload. The first version of the test asserted 400 and was
wrong about the code rather than the other way round. The refusal itself is
unit-tested instead, since the HTTP path never reaches it.

**The scan matched its own docstring.** The first version was
`"get_current_list_name" not in inspect.getsource(mod)` and it failed -- on
`_target_list`'s docstring, which names the function to explain why it is
not called. **Fourth instance of this shape in the project, and the first
where the prose and the checker were written in the same edit.** Replaced
with an `ast` walk over `Name`, `Attribute` and `ImportFrom`: a docstring
naming a function is a mention, not a call. Controls both ways -- a
re-added fallback is caught, and the real module is not.

**Two existing route tests broke, correctly.** Both posted without a list
and expected a plan. The contract changed deliberately, so they now send
one; the test about a blocked rebuild still omits hostname and platform,
which is what it was always about.

---

## The wizard could not onboard the first device of a network

`/onboard/plan` against a fresh list refused with:

    template 'cisco_iosxe/base.j2' is not approved for platform 'cisco_iosxe'

Correct behaviour under scheme 2 -- approval is per repo, keyed on template
hash plus the bound device set, and `Default`'s approval does not carry. The
question is whether it should have been a gate at all.

### Measured: the gate could not be satisfied by any first device

```
approve(fresh_repo, "cisco_iosxe/base.j2", devices=[])
  -> ok: False
  -> "no devices are bound to this template, so there is nothing to
      validate it against"
```

That refusal is **right** -- approving a template against zero devices is the
assertion-over-an-empty-set failure, and it is the one gate in this story
behaving correctly. But it closes the loop:

| | |
|---|---|
| cannot onboard | the template is not approved |
| cannot approve | no devices are bound |
| cannot bind a device | onboarding is how a device arrives |

So a genuinely new network could never onboard its first device through the
wizard. It would have to add one by the legacy CSV path, capture it, extract
host_vars, approve the template, and only then use the tool built for this.

**Only a genuinely fresh list exposes it.** The probe run against `Default`
-- nine devices, an approved template -- would have sailed straight past.
That is an argument for the fresh list being the *right* choice rather than
the artificial part of the probe, and it is the second time in this stage
that the deliberately-empty case found something the populated one could not.

### The gate was keyed on the wrong property

`run_onboarding`'s four steps are credentials, netbox, commit, render.
`render_step` returns `plan.bootstrap_config`, which is
`render_bootstrap()`'s output -- built from the hostname, the one-time
secret, the domain and the management address. **No step reads
`plan.template`.** `cisco_iosxe/base.j2` has no part in producing the
artefact the operator downloads.

This is Phase 3c's rule generalised. There it was *gate on template
fidelity, never on intent drift*, because fidelity is what a render from
intent depends on. The general form: **gate on what the artefact actually
depends on.** Here that is `bootstrap_config.py`, and the path already gates
on it -- platform supported, output sendable as ASCII, address with mask and
interface, name free in both stores.

What the template gate protected is real and is checked where it belongs:
the deploy path validates approval on every plan, per device, with the
offending lines named. Checking it at onboarding was early, duplicated, and
blocking on something fixable in between.

### An advisory has to read as a next step

`OnboardPlan.advisories` is a computed property beside `blocking_reasons`,
never merged into it, and carried as its own key in `summary`. The text
names what cannot be done, why not yet, and what to do:

> You cannot deploy to this device until `cisco_iosxe/base.j2` is approved
> for list `nmas-probe`, which needs a captured device to validate against.
> Onboard this device, capture its config, then approve the template on the
> Templates tab.

A warning about nothing trains the reader to skip warnings, which costs the
next real one.

### The failure mode of this change, and the control for it

**An advisory list that can swallow a refusal.** So the controls assert both
halves, in the shipped renderer:

* an advisory alone -> Create enabled, drawn `alert-warning`;
* an advisory **and** a genuine blocker -> Create disabled, `alert-danger`
  present, and the refusal drawn **above** the note so a long advisory
  cannot push it off the top of the panel;
* no advisories -> no box at all;
* `test_no_step_of_the_run_reads_the_template` -- parsed, not grepped,
  because the docstrings around it name `template` repeatedly to explain why
  it is *not* used.

Two existing tests pinned the old behaviour and were changed deliberately.
`test_three_problems_are_all_reported` used the unapproved template as its
third problem; the property under test is *every reason at once*, not *these
three reasons*, so it keeps its meaning with a real third blocker and would
have lost it with a note dressed as one.
`test_an_unapproved_template_refuses_with_the_reason` was removed, and its
removal is pinned by the class that replaces it.

---

## Third docstring this stage that taught something the code does not do

`render_step` was documented as *"The downloadable artefact, from
**committed** intent."* It returns `plan.bootstrap_config`, rendered from
the hostname, secret, domain and address. The commit runs first and that
ordering is deliberate -- an operator must never download an artefact for a
device the NSoT has no record of -- but **the ordering was described as
though it were the derivation**, and the derivation claim was false.

Three in this stage:

1. `manifest.py`'s slug example;
2. `render_bootstrap`'s *"what remains is what makes the device reachable"*,
   false in its last clause -- what remained made the device **boot**;
3. this one.

All three were load-bearing prose sitting next to correct code, which is the
combination that survives review: the code is right, so nothing fails, and
the sentence is confident, so nobody re-derives it. The pattern to watch for
is a docstring that explains *why* an ordering exists and then names the
ordering as a source.

---

## "Runs against the REAL adapters" was met in name

4C.7's acceptance, set explicitly: *"test_onboard_ordering.py must run
against the REAL adapters."* It was satisfied for three of the four. The
fourth was stubbed:

```python
monkeypatch.setattr("modules.credentials.set_device_override",
                    lambda lst, host, values: overrides.update({(lst, host): values}))
```

The real signature is `(device_key, username, password, secret="")`.

**The stub carried the same misreading as the caller**, because the same
person wrote both in the same sitting from the same wrong idea of the
function. So `bind_credentials_step` passed a list name as the key, a
hostname as the username and a dict as the password; `encrypt_value(dict)`
raises `AttributeError`; `/onboard/create` failed at its first step every
time it ran -- and this test passed, every time.

Structurally identical to the BGP address-families fixtures: **parse and
render flattened symmetrically, so both sides agreed with each other while
both disagreed with the device.** Here the test and the caller agreed with
each other while both disagreed with `credentials.py`.

### Two lessons, and the second is the transferable one

**The assertion was about the shape of a call.** It read a dict the stub had
built -- so it verified that the step called *something* with *certain
arguments*. The property that matters is that the credential the device
boots with is the one `resolve()` hands back for that device, which is what
phase 2 depends on and the only reason the override is written at all. That
property cannot be expressed by comparing arguments, and it was false.

**"Uses the real thing" has to be checkable rather than claimed.** The
acceptance was written, agreed, and recorded as met. Nothing measured it,
and a `monkeypatch.setattr` three hundred lines below the docstring is not
visible from the sentence that promises otherwise. The stub is now gone --
the real function runs against a temp credential store -- because a stub's
signature can drift from what it stands in for, and the stub for the one
adapter nobody had read is exactly where that happens.

The general form, for acceptances yet to be written: **an acceptance that
says "the real X" needs a test that would fail if X were replaced**, or it
is a sentence rather than a check.

---

## The conclusion held; the reason did not

`release()` was built first on an agreed argument: *a name that can be taken
and never given back means one typo permanently consumes a hostname.*

**That trap did not exist.** `commit_step` called `adopt_identity()` and
discarded the return value, so no manifest entry was ever written --
measured: `manifest.load(repo)["devices"]` was `{}` after a successful
commit. `_name_in_manifest` never fired, nothing was consumed, and there was
nothing to release.

Both of us reasoned from a function's **name** and a docstring that was true
about the call and false about the outcome: *"the identity is minted here
and only here"*. It was minted into a local and thrown away. Neither of us
read `adopt_identity` until the abandon tests failed against an empty
manifest.

**The build order was right and the reason was wrong, and those are
different things.** The identity *should* be recorded, it now is, and the
trap becomes real from that commit onward -- so `release()` was built for a
hazard that its own prerequisite created. Worth recording precisely because
"we got there anyway" is the kind of outcome that stops a premise ever being
re-examined.

## The closest call of the stage

`abandon` was scoped to run the NetBox step "through the provenance
Remove". The obvious implementation calls `remove_list_from_netbox`.

It walks **everything** in the created-id record across `_REMOVAL_ORDER`,
which includes `dcim/sites`, `dcim/regions` and `ipam/vrfs`. Abandoning one
failed onboarding on `default` would have deleted every NMAS-created object
in that list **and the shared objects r1-r5 depend on**.

Caught by reading the function before building against it -- the same habit
that caught `set_device_override`'s signature an hour earlier, and the same
one that did not happen for `adopt_identity`. Three data points in one
sitting: reading the API costs a minute, and not reading it has cost a
defect every time.

`remove_device_from_netbox()` is the answer: the device, its interfaces, its
IPs, and nothing else, with shared objects reported as **retained** rather
than skipped.

## Auditing for discarded return values, and what it found immediately

`adopt_identity` was a call whose return value was thrown away, so the
mechanical question is: *what else is?* An `ast` walk over the four
onboarding steps for `Expr(Call(...))` -- a call used as a statement --
found eight, of which six are deliberate (`set_device_override` and
`clear_device_override` return `{"ok": True}` unconditionally,
`upsert_device` returns the entry it wrote, `write_committed` returns a path
and **raises** on refusal, `assert_dialect` raises by design).

**One was a live defect, in code written twenty minutes earlier.**
`repo.git()` returns `(rc, stdout, stderr)` and **never raises** -- 127 when
git is missing, 124 on timeout. `abandon_onboarding`'s intent step called it
twice and discarded both, so a commit that never happened would have been
reported as *"removed and committed the removal"* and abandon would then
have asked `release()` for the name back. In the flow whose entire purpose
is not to do that.

### And the test for it had the same defect it was testing for

The first stub was:

```python
if args and args[0] == "commit":
```

The call is `git(repo, "-c", …, "-c", …, "commit", "-m", …)`, so the first
argument is `-c` and the check never fired. **A stub assuming the shape of
the call it stands in for, inside the test written to catch a stub assuming
the shape of a call.** `"commit" in args` is the fix.

### Which then found a second defect, one layer down

With the stub working, the name was *still* released after a failed commit.
`abandon` does `os.remove(path)` and then commits, so a failed commit leaves
**no file on disk and the intent still at HEAD** -- and `references()`
checked only `os.path.exists`. Release found nothing and handed the name
back while the device's intent was committed.

`references()` now asks git (`cat-file -e HEAD:<path>`) as well as the
working tree, and an unreadable check counts as *referenced*, because a
check that could not run has not passed.

Three defects from one audit, each found by the failure of the fix for the
one before it.

---

## The defect class survived being the explicit target of the test

The strongest instance of "the seam is above the defect" this project has
produced, and it is recursive.

`bind_credentials_step` passed the wrong arguments because a stub in
`test_onboard_ordering.py` had been written from the same misreading. The
lesson drawn was: **a stub's signature can drift from the function it stands
in for.** A test was then written to catch exactly that, for `repo.git()`.

Its stub was:

```python
if args and args[0] == "commit":
```

The call is `git(repo, "-c", …, "-c", …, "commit", "-m", …)`. The first
argument is `-c`. The check never fired, and the test reported the
production code as passing while the defect it was written for was live.

**A stub assuming the shape of the call it stood in for, inside the test
written to catch a stub assuming the shape of a call** -- with the lesson
fresh, the author alert to it, and the defect named in the docstring above
the stub.

So this is not another anecdote. It says the class survives being the
explicit target: knowing about it is not a defence, because the misreading
happens in the same act as the guarding. What works is not vigilance but
**asserting the property instead of the call** -- `"commit" in args` is
still a shape assumption; what actually holds is that the step fails when
the commit fails, which the test now asserts through the step's own result.

## A wrong-and-looks-right state reached through the FAILURE path

Most examples in this project are of a **success that was not one**: a
`success: true` with no tool calls, "all 9 clean" over ten devices, a badge
reading Active over 26 failures.

This one is different and is worth keeping as its own example, because
nothing on the happy path can reveal it.

`abandon_onboarding` removes the intent file and then commits the removal:

```python
os.remove(path)
git(repo, "add", "-A")
git(repo, "commit", ...)      # fails
```

A failed commit leaves **no file on disk and the intent still at HEAD**.
`references()` checked `os.path.exists` and found nothing, so `release()`
concluded nothing named the device and handed the name back -- **a cleanup
that half-ran and then reclaimed the name**, reporting a reference count of
zero that was true of the working tree and false of the repository.

Every test of the successful path passes against this. The state exists only
after a failure, which is exactly when an operator is least able to check.

`references()` now asks git as well as disk, and **an unreadable check
counts as REFERENCED** -- the same rule as *inconclusive is not a refusal*
and *a check that did not run has not passed*, applied to a filesystem.

## Three API reads in one sitting, and they agree

| API | read first? | outcome |
|---|---|---|
| `set_device_override` | **yes** | caught: wrong key, wrong arg types, `/onboard/create` dead at step 1 |
| `remove_list_from_netbox` | **yes** | caught: would have deleted the sites, regions and VRFs r1-r5 depend on |
| `adopt_identity` | **no** | shipped: identity minted into a local and discarded, no manifest entry |

One minute each. A defect each time it was skipped, over three consecutive
opportunities in a single session. Worth keeping as a set rather than three
separate notes, because individually each reads as bad luck and together
they read as a measurement.

---

## The Access values were never set, and the belief that they were is the finding

Reported symptom: `cf_access_team_domain`, `cf_access_aud` and
`cf_access_trusted_peers` all `''` in `user_settings.json`, while
`cf_access_jwks_ttl` (3600) and `cf_access_service_labels` ({}) survived --
which looked like a writer that serialises string fields and leaves the rest.

**It is not a string/non-string split.** The "survivors" are exactly the
keys whose **default equals what is in the file**: `jwks_ttl` defaults to
3600 and `service_labels` to `{}`. Every `cf_access_*` key is at its default;
only the three whose default is `''` look blanked.

### Every writer audited; none of them blanks

| path | behaviour |
|---|---|
| `/settings` POST | per-field `if k in data` |
| `save_integration` -> `base.save_config` | `if key in values`; a blank secret keeps the stored one |
| `/settings/integrations/general` | `if k in keys` allowlist; `cf_access_*` not in it |
| `write_settings` | merges, and refuses undeclared keys |
| `migrate()` | `if key not in settings` -- never overwrites |
| `set_user_setting` | faithful read-modify-write |

**No route, form or function writes `cf_access_*` by name.** There is no UI
field for them. The only code that ever writes them is `migrate()` with
`SEEDS_BY_VERSION = {1: "*"}`, which on a v0 file seeds every key in
`DEFAULTS` -- producing exactly the observed state.

### The mtime is what made it falsifiable

`user_settings.json` was last written **20:25:37**; the posture panel was
read around **21:00**. A file not written after 20:25 cannot hold values at
21:00 and blanks now. There is no write in between because **there is no
write at all** -- so the panel at 21:00 read the same blank file it holds
now.

And the panel cannot invent one: `get_setting()` reads the file on every
call with no cache and no environment lookup, `access_set` is
`bool(value)` rather than key presence, and `trusted_peer_count` is
`len(trusted_peers())`. Explanation (b) -- "the panel reports set for a key
that EXISTS" -- is out in the code as well as empirically.

**So the unexamined premise was "they were set."** The AUD was *given*, in
conversation, as a value to store. That it was given became that it was
stored, and neither of us checked. Identical in shape to the manifest
identity both of us believed was recorded because the function was called
`adopt_identity`. Two in one session, and in both the evidence for the
belief was a name or a sentence rather than a read.

The operational finding is the one underneath: **there is no way to
configure Access through the application.** The posture panel exists because
those gates were *"visible only by reading JSON over SSH"* -- and setting
them still is. A posture you can see and cannot set is 3.2c restated.

## An empty allowlist trusted everyone

```python
peer_trusted = (not allowed) or (peer in allowed)
```

An unset `cf_access_trusted_peers` made `allowed == []`, so **every peer was
trusted** -- a blank silently removing the layer this project calls *"the one
that survives a firewall rule being edited later"*. Two independent
conditions, one of which switched itself off when unset.

**It was masked by the other two values also being blank**, so
`is_configured()` refused first and the composite failed closed. That is the
dangerous kind of safe: restoring the team domain and the AUD **without**
the peer list would have turned verification back on with the peer check
off -- strictly worse than refusing everything, because an assertion
captured from a browser replays from anywhere on the LAN. Which is precisely
what "restore the Access values" would have done if taken as two values
rather than three.

### A test pinned it as correct

```python
def test_an_empty_trusted_list_disables_the_peer_check(...):
    """Blank means 'not configured', not 'trust nothing'."""
    ...
    assert ident.is_identified is True
```

The docstring and the assertion disagree: it says *not configured* and then
identifies the caller anyway. Third test in this project to pin a defect as
intended behaviour, after `test_bgp_address_families_on_r3_r4_r5` and the
`next_ts` key.

`is_configured()` now requires all three, `peer_trusted` is
`bool(allowed) and peer in allowed`, and the refusal **names** the missing
values rather than saying "Access is not configured", which sends an
operator to read JSON.

## Residue hid the guard, again

The conftest guard fires per test, snapshotting `data/lists/` before and
after. Ten tests -- all written in this session -- resolved a path through
`get_list_data_dir()` without patching it, and `get_list_data_dir()` calls
`os.makedirs()`, so **merely resolving a path for an unknown list creates
it**.

They passed here and errored on the deployment checkout because
`data/lists/probe/` already existed locally from an earlier run: the
snapshot at test start already contained it, so nothing was created and the
guard said nothing. **Same shape as `C:/TFTP-Root`** -- an environment
carrying the evidence of the bug satisfies the assertion as truly as a clean
one. Removing the two empty directories reproduced all ten immediately.

The fix is `modules.config.LISTS_DIR`, not the function: a module that did
`from modules.config import get_list_data_dir` at import time holds its own
binding and would still resolve into the live directory, whereas `LISTS_DIR`
is read at call time by every caller.

**And the reporting lesson**: "2,736 passing" was quoted from a tail that
said `2736 passed` with no error line **in this environment**, while the same
commit produced ten errors elsewhere. A pass count is not a run result. Error
counts are now stated explicitly rather than inferred from the last line.

---

## The long fuse: five mechanisms, none of which announced anything

The best example of silent failure this project has produced, and the only
reason it was ever found is that the onboarding wizard refused to create a
device and the operator happened to believe the Access values had been set.

### The chain

1. **`save_user_settings()` opened the real path with `"w"`** — truncate in
   place, no atomic rename. The file on disk is briefly a partial document.
   Defensible on its own: it is the obvious way to write JSON, and
   `credentials._save()` had already been given the correct shape without
   anyone noticing this one had not.
2. **A read arrived in that window.** Two settings requests 10 ms apart is
   enough, and the settings page issues exactly that pair.
3. **`load_user_settings()` caught the `JSONDecodeError` and returned `{}`** —
   making an unreadable file indistinguishable from a first run. Defensible
   on its own: it keeps the settings page up when the file is missing.
4. **The next write persisted that `{}`** plus the one key being set.
   Everything else was gone, including `settings_schema_version`.
5. **The file then read as v0**, so the next settings-panel GET ran
   `migrate()` and seeded **107 defaults** over it. The Cloudflare Access
   configuration materialised as three empty strings, `jwks_ttl: 3600` and
   `service_labels: {}` — the exact fingerprint that looked like a form
   submitting only what it renders.
6. **And `cf_access_trusted_peers` blank meant** `peer_trusted = (not
   allowed) or (peer in allowed)` trusted **every** peer, silently ending
   replay protection.

Each step is defensible in isolation. Each is invisible. The composite
destroys the security configuration of the application and reports nothing —
no error, no log line anybody reads, no badge, no refusal that names the
cause.

### What made it nearly unfalsifiable

Every intermediate belief was reasonable and wrong:

* *"a form submit blanked the string keys"* — the fingerprint fits perfectly,
  and no form writes those keys;
* *"they were never set"* — the mtime supports it, and the acknowledgement
  record refutes it;
* *"the mtime proves they were blank since creation"* — it rules out writes
  **after** 20:25:37 and says nothing about the write **at** 20:25:37;
* *"no code path blanks them"* — true, and irrelevant: nothing blanked them,
  the whole file was replaced by `{}` and then re-seeded.

The audit that finally worked was not of writers but of the **reader**, one
layer below everything the writers do.

### Severity, both halves stated

**The gates were real.** There is exactly one path to a person identity:
`identify()` checks `is_configured()` first, `jwt.decode()` must succeed, and
`_actor_from_claims()` runs only on verified claims. Both `verified=True`
sites are inside that function, and the untrusted-peer one sets
`actor=UNAUTHENTICATED, kind=""` so it can never produce a person. The
2026-09-21 source is byte-identical to today's on every one of those
functions. **Reveal, approve, confirm and publish_remote were never
satisfiable by an HTTP header.**

**The exposure was replay, not forgery.** With the peer list blank, a genuine
assertion captured from a browser and replayed from any host on the LAN would
have been accepted. An attacker needed a real Cloudflare JWT — but the layer
that exists to stop exactly that was off for the whole window. Fixing
`peer_trusted` closed it, and neither of us realised at the time that this was
what it closed.

### The fix, and the split that is the point

**A read on defaults is survivable. A write on defaults destroyed the file.**

* `load_user_settings()` returns `{}` for a **missing** file and raises
  `SettingsUnreadable` for one that exists and cannot be parsed. The damaged
  file is preserved as `user_settings.json.corrupt-<ts>` at `0600` —
  a settings file holds secrets in general, even when this one's are
  already gone.
* `set_user_setting()` lets that raise propagate. `get_user_setting()`
  catches it and falls back, because a read continuing is survivable.
* `save_user_settings()` writes a temp file in the same directory and
  `os.replace()`s it, so a reader sees the old document or the new one and
  never a fragment.
* **The failure reaches the UI**, not just the log: `settings_read_health()`
  feeds `identity.posture()`, and the panel draws it **above** every gate row
  in red — because if the file cannot be read, every row below shows its
  default and looks deliberate. A panel built to make the posture checkable,
  quietly reporting a posture nobody chose, is the same defect one level up.
  `device_manager.log` is not read until something else has already gone
  wrong; that is now measured twice.

Controls both ways, since collapsing the two halves was the defect: a
truncated file must raise (the previous loader returns `{}` — shown), a
missing file must still return `{}` (first run), and a healthy file must
still write (a guard refusing everything would pass every other test and make
the settings page read-only for ever).

---

## The counterpart failure: a resolved fact re-asserted as pending

Two stale premises were caught tonight, both in the same direction —
**believing something was done when it was not**:

* the manifest identity, believed recorded because the function was named
  `adopt_identity`;
* the Cloudflare Access values, believed set because they had been *given*
  in conversation.

This is the third, and it runs the other way: **believing something is
unresolved when the evidence has already resolved it.**

Having established that Access was unconfigured and that `/onboard/create`
therefore answered 403, that blocker was restated **twice more** — after the
operator had reported setting the values, after the posture panel had shown
all three, and after `identity/status` reported `access_configured: true`.

### What makes it the sharp form rather than mere inattention

The refuting evidence was not merely present — **it had already been used**.
The NetBox diagnosis was derived from the run reporting *"Device
onboarded."* That report presupposes `run_onboarding` completed, which
presupposes `/onboard/create` passed its identity gate, which presupposes a
verified person, which presupposes Access was configured. The inference was
made, acted on, and written up — and the belief three steps upstream was
never revised.

So the failure is not "the fact was missed". It is **a fact consumed for one
conclusion and not propagated to another**, which is exactly the shape of
every stale premise in this project: `adopt_identity`'s name was read and
believed without reading the body; a docstring's ordering claim was read as
a derivation; a stub's signature was written from the same misreading as the
caller.

### The check, stated so it is usable

**Before restating a blocker, ask what exists downstream of it.** "Create is
blocked" is refuted by "a device exists that Create made", and that
refutation is available without re-measuring anything — it is already in the
artefacts under discussion.

The general rule: a blocker is a claim about the present, and claims about
the present expire. An established *absence* needs re-checking on the same
schedule as an established presence, and **the arrival of a downstream
artefact is the cheapest possible re-check**.

---

## "The machinery existed and one caller was not using it"

Not a finding but a **class**, and the 4C probe produced four of them in one
session:

* `run_onboarding()` — complete, tested, and reached by nothing;
  `/onboard/create` returned 501.
* `loadOnboardPending()` — a renderer whose only callers were buttons inside
  the banner it draws.
* The banner's Verify and Abandon — reading the wizard's select for a list
  the row already carried.
* `finish_bootstrap()` — phase 2's rotation, built and unwired.

And a fifth, raised at the end and deferred to Stage 7 §6a: `clab-sync`
already writes into `~/labs/lab/configs/` on the containerlab host on a
timer, so the NMAS holds credentials, a path and a mechanism for putting
files on that host — and onboarding asks the operator to download a config
and `scp` it by hand.

**They cluster at the edges of a feature, not in its middle.** Each was
built correctly and left unconnected, and in every case the tests covered
the thing rather than its wiring: `test_onboard_ordering` calls
`run_onboarding` directly, `test_onboard_phase2` executes
`pendingBannerHtml` directly, `test_onboard_wizard_renders` executes the
renderer and not the fetch. **A test that constructs its subject cannot
notice that nothing else does.**

The existing guard for this is the unreachable-function test, and it is
worth stating as a rule rather than a habit: **a feature is not done when
its parts pass; it is done when something a person can reach calls them.**

### The credential-in-Downloads problem, recorded with it

The bootstrap artefact carries a one-time password **in the clear** — a node
cannot boot a masked one. The browser download therefore leaves it in
`~/Downloads` unencrypted on a workstation, which is the one place this
program's rules about secrets do not reach.

So delivery is not only ergonomic. **Any path that avoids the browser is a
security improvement**, and that is the stronger half of the argument for
building it. The weaker half — that `scp`ing files by hand is tedious — is
the one that would otherwise have justified wiring `clab-sync` straight in,
which would have produced a tool that only onboards emulated devices.

---

## A result field scoped to a part, read as the whole

A new variety of the pattern this project keeps finding, and worth separating
from the others.

The familiar shape is **a check that verifies a proxy**: `_list_golden_configs()`
enumerating a directory while content came from the manifest, `ok` meaning
"the sync ran" rather than "the devices landed", a two-byte needle in 953
bytes of ciphertext.

This one is different. `verify_and_promote()` did:

```python
out["ok"] = out["promoted"]
```

**`ok` was scoped to one step and consumed as the verdict on the phase.** The
function's *name* promises two things and its result reports on one — and the
one it reports on is the step that changes what the operator SEES. Everything
that does the work (capture, rotation, RW removal, the golden, the NetBox
record) either failed silently or was never built, and the run returned
`ok: true`.

So the operator saw a promoted device with a full action set, holding a
throwaway bootstrap password, with no golden and an empty credential in the
CSV. **The one step that changes the display ran; the four that do the work
did not.**

The rule: **a result field named for the whole must be computed from the
whole.** If a function's name promises N things, `ok` means all N or it means
nothing — and if only one part can be reported on, the field must be named
for that part (`promoted`, not `ok`).

## A fact recorded where nobody reads it is not a fact reported

The NetBox step **did** report itself. The result carried
`netbox: {"deferred": true, "reason": "…has no captured config yet…"}`,
accurate and complete. Nothing surfaced it: the toast said the device was
promoted, the banner cleared, and the deferral sat in a JSON response nobody
opened.

Identical to the background agent's 26 consecutive failures living in
`data/agent_activity.json` while the badge read **Active, in green** — and to
the drift checker's `disabled` state being visible only by reading JSON over
SSH.

Three instances now, and the common form is worth stating: **the recording is
the easy half.** A value written into a result, a log line, or a state file
discharges the author's sense of having reported it, and discharges nothing
else. The test is not "is it recorded" but **"where would somebody have to
look, and would they have reason to look there?"** — and if the answer is a
response body during a successful-looking run, it is not reported.

This is why `redact.health()` goes in `GET /identity/status`, why the drift
panel says "checked 7 of 9" on screen, and why the pending banner draws its
own read failure above the rows rather than logging it.

---

## What the Stage 4C probe found, and why that is the stage's result

The probe is **half-run**. It has not yet proved the thing it was built to
prove — that the wizard onboards a device end to end and that Remove cleans
up after itself. Judged on its stated acceptance it is incomplete.

Judged on what it produced, it is the most productive exercise of the
project so far. **Every one of these was live in code the suite passed:**

| found | what it was |
|---|---|
| the empty-password connection | phase 2 offered `""` to a device whose credential sat in the store; Netmiko with the staged password reached it on the first try |
| an importer with nothing to import | `sync_list_to_netbox` builds objects from a golden config, and an onboarding device has none — so it created a region, a site and a VRF and no device, and reported *"Device onboarded"* |
| an unreachable banner | `loadOnboardPending()` called only by buttons inside the banner it draws |
| unreachable banner actions | Verify and Abandon reading the wizard's select for a list the row already carried |
| a discarded artefact | `render(plan)`'s return value thrown away — phase 1's entire product existed only on a screen, before Create |
| a settings file that erased itself | truncate-in-place + `{}`-on-unreadable, which took the Cloudflare Access configuration with it |
| a peer check that trusted everyone | `(not allowed) or (peer in allowed)` — a blank allowlist ending replay protection |

**Not one was findable from the suite, and the suite was not weak.** It had
2,700+ tests, negative controls on every new mechanism, floors on the scans,
duktape executing the shipped JavaScript, and an AST checker for removed
definitions. Every test passed throughout — before each defect, during it,
and after.

### Why the suite could not see them

They are not defects *in* units. Every unit was correct:

* `pendingBannerHtml` renders perfectly — nothing called it;
* `render_bootstrap` produces exactly the right config — nothing kept it;
* `sync_list_to_netbox` imports correctly — it was handed a device with
  nothing to import;
* `load_user_settings` returns `{}` on an unreadable file, which is what it
  was written to do;
* `identify()`'s peer check evaluates its expression correctly.

**They live in the relationships between correct parts** — in whether
anything calls a function, in whether a value survives from where it is
produced to where it is used, in whether two stores mean the same thing by
the same name. A test that constructs its subject cannot see that nothing
else does, and a test that mocks a collaborator cannot see that the
collaborator's real signature differs.

### The transferable claim

**Running a thing end to end on real hardware is not a higher grade of
testing; it is a different instrument.** It measures the seams, and the
seams are where every one of these lived.

That is the argument for the probe existing, and it is the stage's result —
more so than the feature, which is still unfinished. A suite proves the
parts work. A probe proves the thing works, and the difference between those
two sentences is seven defects.

## Phase 2's second live failure: "something stopped me and nothing failed"

The first phase-2 run on hardware failed at `rotate` with the device dict
carrying no credentials — fixed, and a real defect. The second run failed at
`rotate` again, and reported:

```
"state": "failed_before_any_change",
"failed_checks": []
```

Two readings, both bad: either preflight refused without naming the check
that refused, or the reporting could not see what did. **Measured rather
than guessed, and the answer was neither** — three separate defects, each of
which alone would have produced the same output and been diagnosed wrongly.

### 1. The refusal was not a preflight check at all

`rotate()` compares `confirmed_fingerprint` against `fingerprint_for(pre)`
**after** preflight has passed. So every check was `ok`, `failed_checks: []`
was *truthful*, and the state was truthful — the two were describing
different exits.

Phase 2 had sent a fingerprint computed by its own
`_phase_two_fingerprint()`, as `sha256("onboard-confirmation|host|ip")`.
That can never equal `fingerprint_for(pre)`, so **every phase-2 rotation
refused, permanently and safely**. It is verbatim the defect that function's
own docstring describes, whose closing line is the rule it broke:

> *Two callers computing the same hash from the same data is a rule that can
> be broken. One function is a rule that cannot.*

The fix is not a second correct hash. Phase 2 is one click running seven
steps: there is no separate plan step, so there is **no window between plan
and apply** for the comparison to protect. `SELF_CONFIRMED` is a shared
sentinel, and `rotate()` records honouring it as a **step** rather than
skipping silently — a check that passed because it did not run is exactly
what the fingerprint was added to stop.

The first attempt at the fix was worse than the defect: it called
`preflight()` inside `run_phase_two()` to hash its result. Correct about the
function, and it put a **live SSH session** inside a function every one of
whose collaborators is otherwise injected — ten seconds of connect timeout
per call, **221 seconds across the suite**. The slowness was the symptom;
the defect is a function whose contract is *nothing here touches the
network* quietly acquiring something that does.
`TestPhaseTwoOpensNoSocketOfItsOwn` asserts it with a socket spy.

### 2. The reason was computed, returned, and thrown away

`finish_bootstrap` read `result.get("error")` — a key `rotate()` never sets
— in preference to `result["reason"]`, which it does. So *"the confirmation
does not match this device's current state"* existed, correctly, one frame
below where it was needed. Same shape as the discarded bootstrap artefact
and the discarded `adopt_identity` return: **a fact produced where nobody
reads it is not a fact reported.**

### 3. The reporting read one field

`_rotation_refusals()` now merges `steps` and `preflight_checks` rather than
choosing, so neither has to be the canonical one, and **an empty answer is
impossible**: it falls back to the reason, then the state, and finally says
the refusal was unattributed — which is a defect report rather than a blank.
The rule the user set for the fix:

> An empty `failed_checks` alongside a failure state must be IMPOSSIBLE, not
> merely unlikely. A state that says "something stopped me and nothing
> failed" is worse than the state before, because the first version at least
> didn't claim to know.

### The controls found two more, and one was in the fix itself

Six negative controls were run. Four reproduced the defects above. The other
two are the finding:

* **The success control.** `_rotation_refusals()` applied its never-empty
  rule to *every* result, so a **successful** rotation reported *"named no
  step — that is a defect in the rotation's own reporting"*. The invariant
  had eaten the distinction it was built to protect. Three tests asserting
  *a refusal is always named* all passed; a function that always returns
  something satisfies every one of them. Only the control asking whether a
  success returns nothing could see it.
* **A control that passed.** Deleting the `SELF_CONFIRMED` branch from
  `rotate()` — which *is* the live failure — left the entire suite green.
  Phase 2's tests inject a stubbed `rotate` and cannot reach the
  comparison; the rotation suite never sent the sentinel. **The seam between
  two tested halves**, for the third time this stage, after `body: '{}'` and
  the three guards in the agent panel. A control that passes is either a
  missing test or a broken control, and telling which is the work:
  `TestSelfConfirmationAtItsOwnSite` is the missing test, and it carries the
  control that the exemption is not the check removed — widening it to
  `if confirmed_fingerprint:` fails seven tests, four of them pre-existing.

Reading that branch to write the test found a fourth, minor defect: the
trailing `_step("confirmation", True)` was unconditional, so the
self-confirmed path recorded the step **twice** — the one result whose job
is to say which branch ran said both.

### Process, recorded because it cost time

Two errors of my own. A `pkill -f "pytest -q"` issued in the same command as
a heredoc killed the heredoc, so one edit silently never landed and was
found by grep rather than by a failure. And three numbers quoted in commit
messages were stale by the time they were read — a pass count is a
measurement with a timestamp, not a property of the branch.

## Step C proven end to end, and the one thing it could not prove

**2026-09-24.** Phase 2 ran clean on `bp-onboard-c`, and every artefact it
was supposed to leave behind is where it should be:

* manifest: `netbox_id 10`, `verified_at 03:42:21`;
* `devices.csv`: encrypted password **and** secret, carrying the **rotated**
  value rather than the empty string that failed twice;
* `golden/bp-onboard-c.cfg`: 6,907 bytes, committed, tagged
  `golden/bp-onboard-c/20260924T034213Z`;
* line 153 reads `username admin privilege 15 secret 9 $9$…` —
  **device-generated**, the bootstrap password gone;
* **no `snmp-server` lines at all** — the RW community was removed *before*
  the capture, so the repository's first record of the device is a state
  worth restoring rather than one we deliberately do not want;
* staging empty — the rotation completed and cleared it;
* `nmas-check-credential bp-onboard-c --expect` → **ACCEPTED, exit 0**:
  resolved through the inventory, connected with what the CSV carries. That
  is the whole chain in one call, and it was **INCONCLUSIVE two hours
  before**.

### The teardown could not be measured, and that is the finding

**Step 2's census baseline was never taken.** Creating the list through the
GUI does not prompt for one, and the `--out` command was lost when the
probe's method moved to the UI path. So the run that proved onboarding end
to end left its **teardown unprovable** — and the teardown is what the probe
exists to prove, the provenance-based Remove having never once run against
objects it created itself.

It is not recoverable after the fact, and that is the whole shape of it: a
baseline taken *now* would contain the probe's own objects, so the teardown
would measure clean while leaving them behind. **Worse than having none.**
There is exactly one moment at which a baseline is truthful, and it is
before the first step that can write.

Three fixes, at three different distances from the mistake:

1. **The baseline is step 0a**, ahead of enabling NetBox writes. It used to
   be step 2, after the list was created — skippable there, and skipped.
2. **Step 12 checks for the file before the Remove**, not after. Discovering
   it at the `--compare` is discovering it once the objects are gone.
3. **`--compare` has three exit codes.** A missing baseline used to raise
   `FileNotFoundError` and exit **1** — which is what *"the teardown left
   objects behind"* exits with. The two most different outcomes the probe
   can have shared a code. It now exits **2** and prints `UNPROVEN`, saying
   in words that this is not a pass and not a failure, that nothing was
   measured, and that a baseline must not be taken now.

Same distinction as `inconclusive` to `failed`, *"checked 7 of 9"* to a
number that reads as complete, and `did_not_answer` to a device verdict. It
keeps arriving because two-valued reporting is the default shape of every
check anybody writes.

The empty-baseline case is the same failure in the file rather than in the
assertion: `{"types": {}}` makes every comparison against it pass. It is
refused for that reason, in those words, and the tests carry both floors —
a real baseline still passes, and a real difference is still a difference —
because a `read_baseline()` that refused everything would satisfy every
refusal test and leave the probe with no acceptance at all.

### Pre-existing, noticed here

`nmas-verify-runbook docs/STAGE4C_PROBE.md` reports *"only 2 commands found
— the scan is not reading the file it claims to read"*. Its floor is firing
correctly: the GUI-method rewrite deliberately removed nearly every
`curl localhost:5000/…`, so there is almost nothing left for it to resolve.
The floor was calibrated against a runbook that no longer exists. Not
touched here; recorded so it is not read as a regression.

## Stage 7 §6b: the tool knows and the screen does not

Verify promoted the device and the device list still read
`nmas-probe (0 devices)` until a manual refresh. Everything had worked and
nothing on screen said so — which leaves the operator not with a stale
number but with **not knowing whether the action worked**, so they press the
button again or go to the shell.

Third instance in one session, each previously fixed as its own bug: the
Remote card's last-push predating the commit just made, the drift panel's
badge from the previous run, and now the device list after promotion.
**Recorded as a rule for the redesign rather than a fourth per-button fix**
— every mutating action names what it *invalidates*, and the panels
displaying that data re-fetch. The action names the data, not the panel,
because the panel that issued the call is usually not the one that is now
wrong: Verify lives in the pending banner, and what went stale was the
device list, the golden panel, the drift count and the NetBox object count.

The rule's own wrong-and-looks-right state is an invalidation **declared and
subscribed to by nothing** — the `next_ts` key the scheduler wrote and
nothing read, and `loadOnboardPending` having no caller. So the check is a
set difference in both directions with a floor on each. The second is a
re-fetch that fails and leaves the old value rendered: confidently wrong is
worse than behind, so a failed refresh marks the panel stale with the time
of the value it is showing.

## Remove deleted two objects it did not create

**2026-09-24, on the real NetBox.** The Stage 4C probe's teardown deleted
`10.0.0.15/24` and `2001:db8::2/64` — r3's containerlab management addresses
from the Lab 1 import. ip-addresses 82 -> 80; total 229 -> 227.

**Every step in the proof of "Remove deletes only what it created" holds.**
The apply reported `ok: true` and `skipped: []`; the eight objects it deleted
were each tagged `nmas-managed` and each in `data/netbox_created_ids.json`;
the provenance gate refused nothing because there was nothing to refuse. The
damage was done by the database, on Remove's behalf, **after the last point
at which NMAS was looking.**

This is the worst failure class in the design: the promise the gate exists to
keep is false, and the gate is working correctly. It is also exactly why the
teardown was run against the real NetBox instead of being proved by dry run.

### The arithmetic says cascade, not a wrong delete list

The eight objects were created after the baseline and then deleted, so they
net to zero against it. **-2 is therefore exactly the two addresses, and
nothing else was lost** — no interface, no device, no VRF or site beyond
NMAS's own. That rules out the alternative explanation (NMAS deleting an
object belonging to something else), which would have shown as -3 with an
interface missing.

So the loss travelled along a link an IPAddress has that is **not** its
interface, since the interface survived.

### The tension that has to be measured rather than argued

The leading hypothesis is the VRF: Remove deleted `ipam/vrfs` id 4
(`nmas-probe`), and a VRF deletion can take addresses assigned to it. But
the two addresses are r3's, in the **`clab-mgmt`** VRF, which Remove did not
touch. Both of those cannot be true as stated, and **which one is wrong is
the diagnosis** — not something to settle by reasoning about Django's
`on_delete`.

`scripts/nmas-netbox-deletions` is the instrument. NetBox records every
deletion in its changelog with the `request_id` of the HTTP request that
caused it, and **a cascaded deletion carries the request_id of the delete
that triggered it** — so the request holding three deletions names the
culprit and its collateral in one row, and `prechange_data` then says what
the collateral hung off. Each of NMAS's eight deletes was its own request,
so one request with more than one deletion is decisive.

Two details in it are the project's own rules applied: the changelog moved
from `extras/` to `core/` in NetBox 4.0, so it tries both and prints which
answered — a 404 on the wrong path would read here as *no deletions*, the
opposite conclusion, and *a lookup that misses is a fact about the query*.
And an empty window says so in words, because NetBox prunes the changelog:
*"that is a fact about the window, not about NetBox"*.

### Why the suite could not see it, and still cannot

`FakeNetBox.delete` pops one object out of a dict of lists. **No foreign
keys, no `on_delete`, no PROTECT, no CASCADE.** Every Remove test measures
NMAS's loop against a store incapable of the behaviour that caused the
damage. Not a criticism of the fake — it is the boundary of what a fake can
prove, and the same seam as everything else this stage found.

The sharp version: **`test_netbox_preview_fidelity.py` is named for the
property that just failed.** *"The preview count is the executed count"* is
a stated architecture decision with a test file of its own, and it is false
in production — eight previewed, ten gone. It passes because the fake cannot
cascade. The claim was always about NMAS's *delete list*; nothing said so,
and the file's name says the opposite.

### The preview lies by construction, not by a rendering bug

`remove_list_from_netbox(dry_run=True)` walks the same `_REMOVAL_ORDER` over
the same created-id record and calls `_nb_delete`, which in a dry run only
records the intent. **Nothing on that path asks NetBox what a delete would
take with it** — there is no dependents query anywhere in the module. The
preview is exactly accurate about NMAS's intent and entirely silent about
the consequence. Same rule the deploy path keeps and this breaks: *what is
confirmed is what happens.*

**And the cascade was already known.** `_run()`'s already-gone branch is
commented *"Already gone, or cascaded by an earlier device delete"* and
calls `forget_created`. The one place in the program that knows a delete can
take others with it **drops the id and continues** — not counted, not
reported, not distinguished from an object a human removed yesterday. A
cascade detector wired to nothing.

### What the fix has to be, and why it is not built yet

A preview must show consequences, which means a **declared dependency map**:
per type, the queries that find what the database will take with it. That
map has to be derived from what NetBox actually does, and deriving it from a
guess is a second wrong thing that looks right — so it waits on the
changelog measurement. Two properties it needs regardless:

* the map is an **allowlist with a floor**, like `_REMOVAL_ORDER`, so a type
  absent from it is absent deliberately rather than forgotten;
* a preview that could not run its dependents query reports **unproven**
  rather than an empty consequence list, since "nothing will cascade" and
  "I could not ask" must not render the same.

## The write, not the delete: the import took two of r3's addresses

**The cascade was diagnosed and the hypothesis was wrong.** Request
`263695a3` deleted **interface id 60** — `GigabitEthernet1` on device 10,
`bp-onboard-c`, the probe's own device — and the database took ipaddress 44
(`2001:db8::2/64`) and ipaddress 22 (`10.0.0.15/24`) with it, both
`assigned_object_id=60`. The cascade is `IPAddress.assigned_object`, not the
VRF; `clab-mgmt` (vrf 2) was never deleted.

So **Remove behaved correctly given the database it was handed.** By the
time it ran, those two addresses genuinely did hang off NMAS's own
interface. The damage was done about forty minutes earlier, by the import.

### `_ensure_ip_address()` matches by value and takes what it finds

```python
params: dict = {"address": address_cidr}
if vrf_id:
    params["vrf_id"] = vrf_id
existing = _nb_first(session, base, "ipam/ip-addresses/", **params)
...
needs_update = existing.get("assigned_object_id") != interface_id ...
if needs_update:
    return _nb_patch(... {"assigned_object_id": interface_id, ...})
```

**Address, optionally VRF, and nothing else** — no device, no interface, no
list. When the hit is assigned somewhere else it re-points it. The docstring
says *"Get-or-create an IPAM IP address assigned to a DCIM interface"*; the
behaviour is get-or-create-**or-take**.

VRF narrowing cannot help here, which is worth stating because it looks like
the fix: r3's address is in `clab-mgmt` and so is every other router's, so
passing the VRF selects the same object.

### It is structural, not a probe accident

Every vrnetlab node answers on the same internal management address.
Measured against the fleet fixtures in the repository — **all five Lab 1
routers carry the identical stanza**:

```
interface GigabitEthernet1
 description Containerlab management interface
 vrf forwarding clab-mgmt
 ip address 10.0.0.15 255.255.255.0
 ipv6 address 2001:DB8::2/64
```

So **one NetBox object has been passed between six devices**, and whichever
import ran last owns it. The census counts two such objects where a
correctly-scoped import would hold ten. This has been happening since the
Lab 1 import weeks ago; the probe did not introduce it, it made it visible
by deleting the interface the object had most recently been moved to.

### Both guards worked correctly and neither could help

A PATCH never adds `nmas-managed` and never records to
`netbox_created_ids.json` — deliberately, and documented. So the stolen
address was correctly classified as **not NMAS's**, and Remove would have
skipped it had it been asked. It died anyway: **provenance protects the
object, and a cascade travels along the relationship**, which nothing
checks. Two correct mechanisms with a gap between them that is neither's
responsibility — the same shape as every other defect this stage found,
one level up.

### The scoping exists, 160 lines below, in a read

`_upsert_device`'s `primary_ip4` fallback searches by address and then
filters to this device's own interfaces:

```python
if iface_id in nb_iface_map.values():
    mgmt_ip_id = h["id"]
```

The scoping the write path lacks is present, correct, and in the same
function — written by someone who had understood the problem **in the one
place where getting it wrong would only have picked a wrong primary IP**,
rather than moved another device's address. *A read that is careful beside a
write that is not.*

### The description is the only trace, and it makes the rest findable

The sync writes `f"{hostname} {interface}"` on every address it touches, so
the field names the **last writer**. An address whose description names a
different device than the one its interface belongs to was taken from that
device and never given back — which is exactly what
`scripts/nmas-netbox-ip-provenance` looks for. It finds damage that is
**still present**; an address taken and later taken back reads as clean
there, and the changelog is where that lives.

### Why the suite could not see this one either

`FakeNetBox` has no uniqueness semantics and every existing sync test
imports devices with distinct addresses. The collision needs two devices
sharing an address value, which no fixture had — so the defect required a
second device on a containerlab fleet, which is precisely what the probe
was. `test_netbox_ip_scoping.py` now asserts the fleet's shared stanza as
the **premise**, with a control that changing one router's address fails it,
so the premise cannot rot silently.

## The fix, as two findings that outlive each other

### 1. The lookup key is the INTERFACE

**Two devices must be able to hold the same address value, and that is not
a compromise.** Every containerlab node answers on `10.0.0.15` inside its
own namespace; the same is true behind different VRFs and in disconnected
management networks. The address genuinely is duplicated and **each
instance genuinely belongs to its device**. One value, many interfaces,
each its own object.

So the question is *"does this interface already have this address"*, never
*"does this address exist"* — which is the scope `_upsert_device`'s
`primary_ip4` read has always used, 160 lines below the write that lacked
it.

Three details worth keeping:

* **VRF narrowing was never the fix**, though it reads like one: r3's
  address is in `clab-mgmt` and so is every other router's, so passing the
  VRF selects the same object.
* **No interface is a refusal, not a wider search.** `_ensure_ip_address`
  raises `UnscopedAddressLookup` rather than falling back to matching by
  address — the fallback *is* the defect, and a caller with no interface has
  no business claiming an address. The one caller that could pass `None`
  (the `primary_ip4` last resort) now logs a warning naming the consequence,
  so the refusal cannot reach a debug line and read as "it already existed".
* **Addresses are compared as addresses, not as text.** `2001:DB8::2/64`
  from a config and `2001:db8::2/64` from NetBox are one address; comparing
  the strings would duplicate the v6 object on every sync. A control that
  removes the normalisation fails.

An address that moves between interfaces now leaves the old object behind.
**That is not a new class of stale record**: this importer never deletes
anything, so an address removed from a config already leaves one. A move
behaves like a removal.

### 2. The cascade gap, which survives that fix

`modules/netbox_cascade.py`. Any delete of any type can take objects with
it, and the preview reported only what NMAS intended.

**`CASCADES` is measured, not inferred from Django's `on_delete`.**
`dcim/interfaces -> ipam/ip-addresses` comes from the changelog of request
`263695a3`: one DELETE, three deletions. `dcim/devices` reaches addresses
**transitively**, expanded by the walk rather than listed under devices, so
the two cannot disagree.

**A type absent from the map is UNKNOWN, never "takes nothing"** — an empty
consequence and an unmeasured one look identical in a preview, and the one
that reads as safe is the one nobody checked. `UNMEASURED` lists the six
remaining types explicitly rather than being derived from the map's keys,
and a test checks it against `_REMOVAL_ORDER` with a floor, so adding an
endpoint to the removal walk without deciding which it is fails.

`ipam/ip-addresses` is **measured-empty** — an empty tuple, a different
claim from absence — because the same changelog request showed the
addresses' own deletion producing nothing further. Leaving it absent would
have made every preview unproven, and a warning that fires on everything
trains the reader to skip warnings.

**A failed dependents query reports unproven**, never an empty list, and
`collateral()` splits what will be taken into NMAS's own and **foreign** —
the question the provenance gate was built to answer and could not, because
it was asked about each object rather than about the consequence.

The modal renders three states: a red block naming each foreign object, a
quiet line for collateral that is NMAS's own, and a separate amber banner
for *"this preview is incomplete… which is not the same as nothing"*. A
clean proven preview renders **nothing at all**, asserted, because a
renderer that always warns trains the operator to click through.

**A control passed, and that was the finding.** Deleting the call site from
the modal left every renderer test green — they execute `nbCascadeHtml`
directly, which tests the render and not the wiring. That is
`loadOnboardPending` having no caller and the `/onboard/create` payload
seam, for the third time: *a test that constructs its subject cannot notice
that nothing else does.* A test now counts calls excluding the definition.

### The repair is a re-import, and it refuses to run early

`scripts/nmas-netbox-repair-addresses`, dry-run by default.

**Nothing on any device was lost** — r3 still has `10.0.0.15` on Gi1 in its
running config — so the addresses come back from the configs that still have
them. But a re-import **with the old code** walks the fleet again and
reproduces the same state, so the script checks that
`_ensure_ip_address` is interface-keyed and **refuses with an explanation
otherwise**. A repair that recreates the damage is worse than no repair, and
the ordering is too easy to get wrong to leave to a runbook step.

It never deletes and never re-points: an address found on another interface
is **reported and left alone**, because moving one is what caused this.
"Nothing to create" says in the same breath that it is a statement about
what was compared and not a claim that NetBox is correct.

## The asymmetry: git is versioned, NetBox is not

Architectural rather than incidental, and worth a plan item.

`config_repo/` is committed, tagged, pushed to a remote and restorable to
any point. **NetBox is a live database this tool writes to with no history,
no baseline and no rollback.** Baselines are commits of `golden/*.cfg` —
device configuration — and they version nothing in NetBox.

Tonight's damage was bounded **only because NetBox's contents are derivable
from the golden configs**. That is a property of what happened to be
damaged, not a guarantee. Anything hand-curated — a site description, a
custom field, a tenant, a rack — has nothing to restore it from, and the
Phase 0 note that *"the reference NetBox was populated by hand from the
design document"* says the risk was there from the start.

**Plan item: what, if anything, backs up NetBox.** It has its own export,
and `scripts/nmas-netbox-census` already snapshots identity per type — which
is most of a backup already. Had one been taken routinely, tonight's damage
assessment would have been a **diff rather than an investigation**.

## The repair examined nothing and said so carefully

The first dry run printed *"Nothing to create"*. It had examined **zero
devices**.

`plan()` called `load_saved_devices(list_name)`. **That function takes a
path** — `load_saved_devices(csv_path)` everywhere else in the codebase.
Handed a name it failed to resolve the owning list, fell through to a CSV
that is not there, and returned `[]`. The loop ran zero times and every
count downstream **honestly** reported zero.

**Fifth inferred-signature defect this stage**, after
`set_device_override(list, host, dict)`, `preflight`'s lambda, `_commit`'s
spy, and — recursively — the `args[0] == "commit"` stub inside the test
written to catch stub drift. The rule keeps being right: *read the
signature.*

The tell was in the output and it took the operator to see it: `default` and
`Default` produced **identical** results, which means nothing downstream
depended on the argument at all.

### The floor matters more than the defect

*"Nothing to create — examined 0"* is a vacuous pass wearing a careful
parenthetical, and that parenthetical was the only thing standing between
the reader and a clean bill of health. **For a repair script the wrong
conclusion is "the fleet is already correct"**, which is worse than the
usual version of this failure because it ends the investigation.

`plan()` now **refuses** when it resolves no devices, naming the list, the
path it looked in, and whether the file was absent or present-and-empty. An
examination of zero things is not a result — the same rule as every scan's
floor, applied to the tool built to repair the damage those scans found.

### The argument is now meaningful, so an unknown one refuses

`resolve_list()` reads the registry: a name **or** its slug resolves, and
both report the **registered** name so the output cannot be ambiguous
(`nmas-probe` / `nmas_probe` already cost a runbook correction). Anything
else is refused with the known lists named.

**Deliberately not `get_list_data_dir()`**, which calls `os.makedirs()`: a
typo at a repair script would otherwise silently *create* a list. The test
asserting this is **parsed, not grepped** — its first version matched the
docstring explaining why the call is absent, which is the fifth instance of
*the better the comment, the more likely it quotes the code it explains.*

The argument is also checked **before** NetBox, so a wrong list name is not
reported as a configuration problem — the same correction as a bootstrap
render failure announced through `unsendable`.

### The goldens are intact, and that is load-bearing

r3's golden still carries `ip address 10.0.0.15 255.255.255.0` under
`GigabitEthernet1`. So *"nothing was lost, the addresses are derivable from
the configs"* holds as a **measured fact** rather than an expectation, and
the NetBox damage is recoverable. Every claim about this being repairable
rests on that one check.

## NetBox cannot represent the emulator, so the emulator is not modelled

The repair ran and **NetBox refused four of five**:

```
Duplicate IP address found in global table: 10.0.0.15/24
created 1 (r1, id 84), failed 4
```

The script behaved correctly — errors verbatim, and a second run recomputed
against the new reality instead of repeating its plan — and the state is no
worse, only redistributed: r1 holds the v4, r5 the v6, three Gi1s empty.

So it became a design question with three honest answers: **(a)** disable
global uniqueness so NetBox can model namespaced duplicates, **(b)** do not
model containerlab management addresses at all, **(c)** leave it and accept
NetBox is wrong about four interfaces.

**(b), and the deciding argument is the test set earlier in this stage:
would this make sense on a network the tool did not build.** A containerlab
management address would not exist on real hardware — no device has
`10.0.0.15`, it is unreachable from anywhere, and NMAS reaches the fleet on
a different range entirely. Importing it teaches NetBox about the emulator's
plumbing rather than about the network. **(a) weakens a genuinely useful
check to accommodate an artefact**, and the check is the only thing that
made the duplication visible at all.

### A setting, not a constant

`netbox_excluded_vrfs`, defaulting to `["clab-mgmt"]` — another lab's
emulator will name its management VRF something else, the same
network-agnostic rule that already makes the TFTP root and the Jenkins shell
settings.

It is the **second deliberate exception** to *"every new default reproduces
the behaviour that predates the setting"*, after `netbox_allow_writes`, and
for a different reason: the prior behaviour is not a behaviour anybody
chose, it is an error NetBox returns. Defaulting the exclusion to empty
would preserve that error on every install in the name of a rule written to
prevent surprises.

Three details:

* Read through **`settings_schema.get_setting()`**, which falls back to
  `DEFAULTS`, not `config.get_user_setting()`, which reads only the file and
  returns `None` for a key no install has ever written — that would exclude
  nothing, silently, on every install predating the setting. An unreadable
  settings file falls back to the default too: a read is survivable, and
  silently dropping the exclusion is not.
* **The interface is still modelled.** `vrf forwarding clab-mgmt` really is
  configured on the devices; it is the addresses inside the VRF that
  describe the emulator. The skip sits after the interface is created, and a
  test pins that ordering.
* **The skip is counted**, in `ipam_stats` and in the log. A skip nobody can
  see is the failure mode this stack is most prone to.

### The two surviving objects are removed, not left

r1's v4 (id 84) and r5's v6 (id 23). Removed, and the argument is that
leaving them is the worse of two bad options:

* each is **wrong in a specific way** — it claims one device has an address
  that all five have, and a half-true record reads as complete;
* **nothing will ever update them again.** The exclusion makes them
  unreachable by the import: no future run touches, corrects or removes
  them. That is precisely the state the drift checker and the census exist
  to prevent — a store describing something that does not exist, with
  nothing reporting it;
* they **hold the globally-unique slot**, so while they exist nothing else
  can legitimately use that value.

`--remove-excluded` is dry-run first and **provenance still governs**: only
objects tagged `nmas-managed` *and* in NMAS's created record are eligible,
and anything else is reported as left alone. This clean-up is not an
exemption from the gate that the rest of tonight was about.

A device's `primary_ip4`/`primary_ip6` is a **blocker, not a warning** —
deleting one sets the device's primary to null, which is a consequence of a
delete that the cascade map does not cover, **because it is a modification
rather than a deletion**. Worth noting as the map's first known edge: it
answers "what will be deleted", and "what will be changed" is a different
question nobody has asked yet.

## The mode that had never run, and what the controls were actually run against

`--remove-excluded` crashed on its first invocation:

```
NameError: name '_remove_excluded' is not defined
```

**The function was in the file** — at line 347, below the
`if __name__ == "__main__"` guard at line 343. Run as a script, `main()`
executes and returns before Python reaches the definition. I had appended
the new mode to the end of the file without noticing the guard was already
there.

### What the five controls were run against, plainly

Three of the five exercised **`excluded_residue()`** — the planner: the
provenance skip, the `primary_ip` block, and the VRF scoping. The other two
exercised the import-side exclusion. **None of them touched
`_remove_excluded`**, the mode that wires the planner to the CLI. So the
claim "five controls shown failing" was true and did not cover the thing
that was broken.

**And a test that called it would have passed anyway.** The suite loads a
script with `SourceFileLoader(...).exec_module()`, which runs the whole file
with `__name__` set to the module's name — the guard never fires, every
definition is reached, and `_remove_excluded` exists. The harness's import
cannot exhibit the failure, which is the same shape as `FakeNetBox` being
unable to cascade. **The check therefore has to be about the file, not
about the loaded module.**

### Sixth instance, and the purest

Not a wrong signature (`set_device_override`, `load_saved_devices`,
`preflight`'s lambda, `_commit`'s spy) and not an unreachable branch — a
call to something that is not there. The common cause every time: *the test
names or constructs its subject, so it cannot notice that the caller does
not.*

### The check, over the whole directory

`tests/test_script_entry_points.py`, two AST walks across every script:

* **`definitions_below_the_guard()`** — module-level definitions the entry
  point can never reach. Not dead code: code that exists for every reader
  and every test and not for the program.
* **`unresolved_calls()`** — called names nothing in the file or its imports
  binds. Deliberately conservative (a name counts as bound if anything
  anywhere in the module binds it), so it cannot catch a scoping mistake and
  does catch a call to a function that is simply absent.

Both run parametrised over all 29 scripts, so the cost of covering the next
one is zero. With `_the_scan_finds_something` floors on the script count,
the parsed statement count, **and** the number of scripts that actually have
a `__main__` guard — without that last one the ordering check would pass by
finding no guards at all.

`TestTheCheckItselfCanSayNo` drives both detectors against files built to
fail, plus the control on the control: the same file with the definition
*above* the guard is clean, so the detector cannot simply always fire.

The live control is the decisive one: restoring the original ordering
reproduces the `NameError` verbatim **and** fails the sweep by name.

`scripts/nmas-verify-runbook` already does the equivalent for routes,
resolving documented URLs against `app.url_map` rather than trusting that a
blueprint path looks right. Scripts had no such check; they do now.

## The clean-up looked in the wrong place, and NetBox had already said so

`--remove-excluded` reported **0 eligible, 0 not-NMAS's**, against a NetBox
holding id 84 (`10.0.0.15/24`, created by the repair, tagged and recorded)
and id 23 (`2001:db8::2/64`, from the Lab 1 import).

**Measured rather than inferred, and the mechanism was not the one
predicted.** The query it issues is `GET /api/ipam/ip-addresses/` with **no
filter at all**; the match happens client-side on the nested `vrf.name`. So
it is not a name-vs-id filter — but it has the identical signature, because
the field it matched on is **null**.

**The evidence was in NetBox's own refusal, an hour earlier:**

> Duplicate IP address found in the **global table**: 10.0.0.15/24

The repair's `_ensure_ip_address()` call passes **no `vrf_id`**, so id 84
was created in the global table. There was no VRF name to match, the loop
skipped it, and the counters honestly reported zero — while the output said
*"examined every address in clab-mgmt"* about an object that was never in
clab-mgmt. The vacuous-pass shape, in the mode fixed an hour before for a
different reason.

### Two defects, and the second is the one worth keeping

1. The repair created the object with no VRF.
2. **Matching on NetBox's VRF field was a second copy of the exclusion
   rule.** The rule is defined on the config — `vrf forwarding clab-mgmt` in
   the golden — so the import reads it there and the clean-up read it
   somewhere else. Two copies of one rule is how they come to disagree, and
   here they did: one excluded the interface, the other could not see it.

Both now go through one `walk()`: the import, the create path and the
clean-up read `intf["vrf_name"]` from the same goldens. The report names
the **config VRF and the NetBox VRF separately** (`config vrf clab-mgmt,
netbox vrf global`), because the gap between them is the finding.

The create path applies the exclusion too, and **says so** — a repair that
recreated what the import excludes would put the damage back one command
later, in the global table again.

### The floor: what it examined has to be a claim it can support

*"Examined every address in clab-mgmt"* was not. The mode now reports
devices, interfaces seen in NetBox, **how many of those are excluded**, and
how many addresses sit on them — and distinguishes *"no interface in any
golden is in an excluded VRF"* (supportable, and a different fact) from
finding nothing on the interfaces it did identify. An empty
`netbox_excluded_vrfs` **refuses** (`NoExclusion`) rather than reporting
nothing to do: it cannot be cleaning up an exclusion that does not exist.

### The sweep for name-keyed filters: a real negative

Asked for across `netbox_client`, because *a filter that matches nothing is
indistinguishable from a resource that is absent*. Parsed all `_nb_get` /
`_nb_first` calls: **37 filtered reads, and none filters a relation by
name.** Relations are keyed on ids throughout — `device_id`, `site_id`,
`interface_id`, `tunnel_id`, `termination_id` — and every `name=` / `slug=`
filters an object by its **own** identity field, which is what those
filters are for and is not the defect.

So both of tonight's instances were **outside** this module: an ad-hoc
`?vrf=<name>` query, and the clean-up's client-side match. The rule is
pinned anyway, with a floor on the number of reads parsed, a **positive
anchor** naming the id-keyed filters it expects to find, and a control that
introducing `vrf="clab-mgmt"` on a read fails it — because "no offenders"
is also what a scan that could not run produces.

## The edge caches HTML and not JSON, and that looks exactly like a rendering defect

**2026-09-24.** `/golden/baselines` returned `partial: true`,
`inventory_size: 10`, `missing_devices: ["r6"]`, and the Baselines panel
drew a bare *"9 device(s)"*. With `?x=1` it drew
*"9 of 10 — partial · predates r6"*. The code was correct throughout;
**Cloudflare was serving hours-old HTML while the JSON came through
fresh.**

### Why the two halves disagree

The app is reached through a Cloudflare tunnel. The edge caches the
**HTML** and does not cache the **JSON** the page fetches, so a page can be
arbitrarily old while every endpoint it calls is current. **A browser
hard-reload does not bypass it** — `Ctrl-Shift-R` clears the browser's copy
and asks the edge, which answers from its own.

So the signature is precise and easy to read once seen: *fresh data,
stale rendering, and a hard reload that changes nothing.*

### Every "the data is there and the page ignores it" symptom now has two explanations

They are **indistinguishable from the browser**, and the discriminator is
one command that asks the origin directly, bypassing the tunnel:

```bash
curl -s http://10.0.0.211:5000/ | grep -c '<helperName>'
```

* **≥1** — the origin serves the current page. The staleness is between the
  origin and the screen: purge, or `?x=1`, and the code is not the problem.
* **0** — the origin does not have it. Now it is a deploy or a code
  question, and only now.

**Run it first.** It is one command and it partitions the space; every
minute spent reading a renderer before running it is spent on the wrong
half.

### The misattribution is the finding, not the cache

Four defects of the shape *"computed, carried to the browser, drawn
nowhere"* had been found the same night — `loadOnboardPending`, the pending
banner's buttons, `nbCascadeHtml`, and `_gBaselineCoverage`'s route fields.
By the fifth report the prior was so high that the diagnosis was made
before the measurement.

**The more instances of a shape you have found, the more likely you are to
misattribute the next thing that resembles it.** A pattern that has been
right four times is exactly the one to distrust on the fifth, because
confidence is what stops you running the cheap discriminator.

What recovered it was measuring instead of agreeing: rendering the page
through `app.test_client().get("/")` showed **one** baselines table, **one**
`baselines.map`, and `${_gBaselineCoverage(b)}` present in the output. The
correct response to a report that contradicts a measurement is to say so,
not to edit correct code — which is the same rule that kept
`_ensure_ip_address` from being "fixed" by VRF narrowing.

### Consequence for deploys

If the edge caches the app's HTML, **every deploy needs a purge or users
see a stale page while the API is current** — including, at the worst
moment, a page whose safety-relevant fields have changed. Scoped as
[NSOT_STAGE7_GUI.md](NSOT_STAGE7_GUI.md) §6c.

## §0b then §6c: the two cache policies are opposites, and that is the design

Implemented in that order because the pairing was the better finding.

### §0b — 275 KB of script out of the HTML

Measured first: **280 KB of inline script contains no Jinja** and 166 KB
does. The Jinja-bearing blocks cannot move verbatim — that is what
`test_inline_javascript.py` exists to record — so the extraction took the 24
pure blocks over 2 KB and left the rest.

**656,200 → 378,052 bytes of document**, with 284,662 bytes now in
`static/js/gen/`. Fixed page cost **647,383 → 365,417**, a 44% reduction.

**The total first load did not shrink** — 656 KB in one uncacheable
document became 378 KB of HTML plus 285 KB of JavaScript, marginally
*more*. That is the point rather than a disappointment: the 285 KB is now
cacheable and the 378 KB is not, where before one figure had to be both.
**The number that improves on a second visit went from zero to 43%.**

### It broke 166 tests, and that was the finding worth having

Twenty-three files, because the renderer tests read *the source the browser
executes* — which was the template and is now the template **plus** what it
references. Reading the template alone would have made them pass by finding
nothing: the suite built to catch "defined and never called" would have
reported every extracted function as absent, or worse, as present-and-fine.

`tests/js_source.py` is the one answer: `read_shipped(path)` for template
reads and `with_loaded_scripts(html)` for the tests that already read the
rendered page. The second is **strictly more faithful than before** — it
models the program the browser assembles rather than one file that happened
to hold all of it.

Two details cost a round each and are worth keeping:

* the appended script must be **wrapped in `<script>`**, because tests slice
  the page into blocks — appending it bare made `_scripts()` return nothing
  and the assertions then read *"no block defines loadRemotePanel"*, a scan
  finding nothing while wearing the words of a real defect;
* and **one `<script>` per file**, not one for all, because a test that
  indexes into a block (`block[block.index("} catch (")]`) would otherwise
  find a construct belonging to a different extracted file.

`test_scale.py` did its job exactly as designed: the pinned number moved and
the test demanded a new measurement rather than widening a tolerance.

### §6c — the header, and what each half is for

`@app.after_request`, four behaviours, all measured on the response rather
than read from the code:

| | policy | why |
|---|---|---|
| HTML | `no-cache, must-revalidate` + **ETag** | never reusable; the ETag makes revalidation a **304 and zero bytes** |
| versioned `/static/` | `public, max-age=30d, immutable` | changes only on deploy |
| unversioned `/static/` | `no-cache` | a long lifetime on an unversioned URL is the HTML problem one layer down |
| JSON | `no-store` | per-request live state, several identity-scoped |

**`no-cache`, not `no-store`, and the ETag is what makes that true.**
Measured before adding it: the page carried no `ETag`, no `Last-Modified`
and no `Cache-Control` at all, so a bare `no-cache` would have been a full
re-download every navigation — the pairing argument for doing §0b first
rested on exactly that, and with a validator it is a 304.

**The static branch was nearly the hazard it was written to avoid.**
`setdefault` lost to Flask's own `Cache-Control: no-cache` and measured as
`no-cache` on a 27 KB extracted script — undoing §0b in the commit that
depends on it. Caught by **measuring the response**, not by reading the
code, which is the only reason it was caught at all.

**A long lifetime needs versioned URLs or it is the same defect again**: a
deploy changes the file and every browser keeps the old one for a month.
`@app.url_defaults` puts the file's mtime in every
`url_for('static', ...)`, so a changed file is a different URL — nothing to
purge and nothing to remember. Two files in `base.html` reference
`/static/...` literally, never get a version, and correctly fall to
`no-cache`; that is asserted rather than assumed.

### JSON: confirmed, not assumed

Measured before deciding: JSON responses carried **no `Cache-Control`, no
`ETag`, no `Last-Modified`**, and the edge did not cache them — which is
precisely why the API stayed fresh while the page went stale. **That
freshness was somebody else's default, not our policy**, and the whole
argument for putting this in the app rather than in a Cache Rule is not to
depend on one. So it is stated: `no-store`, because these are per-request
reads of live state, several of them identity-scoped, never reusable — a
copy retained by an intermediary is a small exposure rather than a small
saving. Harmless to the client: a `fetch` of an uncacheable response behaves
exactly as it did when the header was absent, asserted by parsing the body.

## Coverage inherited, not designed — the second instance, found the same way

**Nine devices survive a clab host reboot because a pipeline built weeks ago
covers them. The tenth does not, because it was added by a newer path that
did not inherit it.**

r6's startup config lives at `~/labs/r6/configs/r6.cfg`; clab-sync harvests
from Oxidized and writes to `~/labs/lab/configs/`. So a reboot brings r6
back on its bootstrap config — `password 0`, no rotated credential, NMAS
locked out of a device it manages. Stage B's failure by another route, live
from the moment onboarding finished.

This is the drift check's finding again, in a different subsystem. There,
the nine reference devices were checked only because their pre-migration
files happened to still sit in `golden_configs/`, and a device onboarded
after the migration was checked by nothing while its config sat in
`config_repo/`. **The coverage was inherited, not designed**, and it was
invisible because the population that had it was the only one anybody
looked at.

**The generalisation is worth more than either instance:** a property that
holds for the original population and silently does not for anything added
afterwards. It comes from the same cause every time — a capability wired to
*a list that was current when it was built* rather than to the population as
it is now — and both instances were found by **adding one member**. That is
the cheapest available test for the class, and it is what onboarding r6 was
always going to be good for.

### The scoping found a worse half than the sync

Recorded in [R6_PERSISTENCE.md](R6_PERSISTENCE.md). Three settings describe
**one** lab, and `verify_startup_applies()` — the guard that keeps the
rcn-lab1 redeploy ban lifted — resolves `clab_launch_patch` internally,
defaulting to `labs/lab/patches/c8000v-launch.py`.

Today r6 fails closed, because the config path is wrong too and the file is
not there. **Fixing only the configs directory would create the dangerous
state**: the guard would read rcn-lab1's patch, which has the user-skip,
while r6 boots from `labs/r6/patches/c8000v-launch-adopted.py` — verifying a
file that is not the one in play, and **passing**. The precise hazard it
exists to prevent, wearing a green result.

So the three settings must move together, which is one of the four reasons
the answer is a **device → lab map** rather than a second sync target. The
strongest of the others: `verify_startup_file()` and
`verify_startup_applies()` are **already parameterised per call** — only the
defaults are installation-wide. *The machinery existed and one caller was
not using it*, for the sixth time, still clustering at the edges of a
feature.

**Necessary and not sufficient**: the sync script is outside this repository
and writes to one directory with no argument. Until it accepts a target or
learns the map, NMAS resolving the right path changes nothing about where
the file lands — and building the NMAS half alone would produce a system
that verifies the correct path and still writes the wrong one.

## A stated problem narrower than the real one — three times, and the correction always came from reading

Recorded by the operator, unprompted, and it is the most transferable thing
from this stretch:

| stated | actual |
|---|---|
| *"Remove deleted two objects it did not create"* | the **import** had moved them onto NMAS's interface forty minutes earlier; Remove was correct given the database it was handed |
| *"the Cloudflare Access values are empty in the file"* | the settings file **erased itself**, through five defensible mechanisms composed |
| *"clab-sync points at rcn-lab1 and doesn't know about `~/labs/r6`"* | the path is the survivable half; **`clab_launch_patch` is the dangerous one**, and a configs-only fix would have been accepted as complete |

**Each correction came from reading the code, not from the symptom.** The
symptom is generated by the defect's *last* step, so it describes the place
the failure surfaced rather than the place it began — and a fix aimed at the
symptom is complete by its own measure and wrong by the system's.

The third is the sharpest because the wrong fix **would have passed its own
acceptance**: configs directory corrected, file appears, sync reports
success. What it would also have done is point the launch-patch guard at
rcn-lab1's copy for a device booting r6's — turning a check that currently
fails closed into one that passes wrongly. *The narrower problem statement
produced a fix that made the system worse while satisfying the request.*

The practice this argues for is already the project's: **read the function,
do not infer it** — extended from signatures to problem statements. A stated
problem is a hypothesis with a symptom attached, and the cheap discriminator
is usually one file away.

## `clab_host` was set, and then it was not — reading the record

**The question:** if `clab_host` was empty on 2026-09-22, Stage 2's item 2.2
acceptance — *"the `startup_applies` stage runs on a real rotation and
passes for a C8000v because the launch script carries the skip, demonstrably
failing if the skip is removed"* — was recorded as met while the check
refused.

**The record says otherwise, and it is this project's own notes.** "Four
controls that could not fail, in one stage", control 4:

> It ran against the live host with the marker renamed and reported
> **APPLIES for all five routers**, with the same reason text naming the
> helper.

`nmas-check-startup-applies` passes **no `clab=`**, so it resolves
`get_setting("clab_host", "")` — and with that empty it returns
`{"ok": False, "error": "clab_host is not configured"}` and reads nothing.
It cannot produce "APPLIES for all five routers" with a reason naming a
helper it found inside a remote file. **So `clab_host` was set then.**

More than that: the marker-rename run is the check being **calibrated** —
watched failing when the property was false, which is the only evidence a
check measures anything. That is the strongest form of the acceptance, and
it happened.

### The narrower true statement

The **function** has run, on the live host, and has been calibrated. The
**stage** — `startup_applies` inside `persist()` — is a different claim, and
`nmas-check-startup-applies`'s own docstring says why it exists:

> the only way to reach it was to perform a **real rotation** — a new random
> password on a live device. The Stage 2 runbook asked for exactly that,
> minutes before a redeploy whose post-items verify those same credentials.

So the stage, *as a stage of the chain*, likely has never run. That is worth
knowing and it is not "one stated guard has never run".

### What actually happened to the setting

`clab_host` was set on 2026-09-22 and is empty now. Between those, on
2026-09-23, **the settings file erased itself** and a version-0 reseed wrote
107 defaults.

`clab_host`'s default is `""`. So is `clab_sync_script`'s and
`yang_push_script`'s. `clab_configs_dir` and `clab_launch_patch` have
plausible **non-empty** defaults and survived *looking correct* — which is
why the loss was invisible for two days and surfaced only when somebody
asked why a verification had never produced a sha.

**The erasure's blast radius was assessed as "the Cloudflare Access values"
and it was wider.** That is the fourth instance tonight of a stated problem
being narrower than the real one, and the first where the narrow statement
was mine.

### `nmas-settings-diff` cannot find these, by construction

It lists what **differs** from the default; a key reset to its default is
equal to it. **The loss is recoverable from knowledge, not from
measurement**, which is why `settings_schema.GUARD_GATING_EMPTY_DEFAULTS`
is written down rather than derived — three keys today, each one a guard
that becomes a refusal when it is blank.

A refusal fails closed, so nothing broke. It is also **indistinguishable
from a guard that ran** unless somebody reads the reason, which is the
property that let this sit for two days.

## The live run found the map bypassed by the caller that checks it

**Result 1, good:** r1–r5 verify properly for the first time since the
erasure — `dmarchak@10.0.0.210:labs/lab/patches/c8000v-launch.py@e483dd2475b5`,
named with a sha. The guard is running.

**Result 2, the defect:** r6 read
`dmarchak@10.0.0.210:labs/lab/configs/r6.cfg` — the **default** lab's
directory — while `clab_target_for('Default', 'r6')` returned
`labs/r6/configs`.

`nmas-check-startup-applies` passes no target, and both verifiers **fell
back to `get_setting()`** when the caller passed nothing. The map existed
and one caller was not using it, **by omission** — which is precisely the
failure mode a default fallback is built to create. Seventh instance of that
class, and the first **inside the thing built to prevent it**.

It failed closed only because the file was absent. **The same accident that
made the configs-only fix look safe**, twice in one feature.

**The fix is the removal, not a correction.** `_resolve_target()` is the one
path and the direct `get_setting` reads are gone, so a caller that omits the
target gets the device's own lab rather than the default one. `_lab_of()`
with an empty `list_name` **derives the active list** rather than assuming
`default`: a read may derive it, and the alternative here is not a refusal
but a *wrong answer*. The control is the one the operator named — a device
whose lab differs from the default reading its **own** paths, which is what
r6 now provides, with a floor that a default-lab device still reads the
default.

**Result 3:** `--stray` called `os.listdir` on a directory that is on the
clab host while the script runs on the NMAS. `FileNotFoundError` is the
least informative possible answer to *"is there litter on the clab host"* —
it names a local path that was never going to exist and says nothing about
the remote one. It now lists over `ssh` using the host the map carries (a
fourth column), `strays()` is pure with the listing passed in, and a failed
listing is **`REFUSED … not the same as finding no litter`** rather than an
empty result.

### And a control caught me deleting the tests

Rewriting the `--stray` tests with a truncating edit removed
`TestEveryVerifierGoesThroughTheResolver` entirely, along with two others
below it. Controls A and B then **passed** — which is what surfaced it, 22
tests having quietly become 18.

`check_removed_definitions.py` cannot help here: it exits non-zero when a
removed definition is **still called**, and *nothing calls a test*. So the
only backstop for deleting a test is a control that was passing before and
should not be — which is the argument for running controls after an edit to
the test file and not only after an edit to the code.

## "Applies" is a true answer to a different question

`nmas-check-startup-applies r6` reported **APPLIES** — *"the password form
applies behind the injected line; the device ends up with this
credential"* — while r6's startup file held the **bootstrap** credential.

The statement is correct. A `password 0` form genuinely does apply behind
vrnetlab's injected line, and the device genuinely does end up holding it.
What it *means* for r6 is **"this device will come back on a credential NMAS
does not hold"**, and the tool printed it green.

**Worse than the absent-file failure it replaced, because that one was loud
and this one was green.** Eighth instance of the class tonight, and the
second where a composite was safe by an **accident of ordering** rather than
by design: inside `persist()` the presence stage runs first and stops the
chain, so the truthful-but-irrelevant answer is never reached. Read
directly, that ordering was not there.

### The fix is the checker, not the function

`verify_startup_applies()`'s question is legitimate and its answer is
correct. What was missing is that **nothing asked the presence question on
this path**, so the checker now asks both, presence first, and reports the
composite — *"the file does not carry the credential NMAS holds"* outranks
*"the form would apply"*.

### The presence question needed a source

`verify_startup_file()` greps for a `new_hash` the caller just generated. A
checker run after the fact has none, and a `$9$` hash carries a per-hash
salt, so it **cannot be recomputed** from the plaintext NMAS holds.

`verify_startup_carries_current()` compares the startup file's `username`
line against **the same line in the device's own golden** — the captured
record of what the device is running, which `nmas-check-credential` is what
proves NMAS can still use. Equal means a reboot brings the device back as it
is now. It is a real chain from artefacts NMAS already has, rather than a
hash nobody can reproduce.

Three states, not two: **matches**, **does not match** (naming what a reboot
would do), and **inconclusive** when there is no golden to compare against —
because with nothing to compare, *"the file holds a credential"* says
nothing about whether it is the one NMAS can use.

### The form is always named, and the value never is

*"Applies"* must never be printable without saying **what** applies — that
is the entire distinction between the two questions. So the result carries
the `username` line it found and the printer shows it.

`_redact_value()` keeps the form and drops the value:
`username admin privilege 15 secret 9 <redacted>`. A checker that prints the
hash has put the credential in a terminal buffer and a scrollback, and the
question was which form applies.

When presence loses, the applicability answer is **still reported** and
still labelled true — *"(the form WOULD apply on boot — that is a true
statement about a different question)"* — so nobody reads the composite as a
verdict on applicability it never reached.

### It is also the acceptance for the sync half

r6 must read **NOT SAFE** now and go green **only** once its startup file
carries `secret 9`. One test, two purposes, which is what makes it worth
having: `test_a_bootstrap_file_reads_NOT_SAFE_even_though_it_applies` and
`test_and_goes_green_once_the_file_carries_secret_9`.

## A running config is not a startup config — and I reasoned past the reason

**Proposed:** build startup files from goldens rather than from Oxidized, so
a redeploy restores the approved state.

**Wrong, and the sanitizer's own header says why.** It is not cleaning up
Oxidized's quirks. It compensates for two facts about **running configs in
general**:

1. **`no shutdown` re-injection** — a running config records `shutdown` on a
   down interface and **nothing** on an up one, so any harvested config
   brings every addressed interface back admin-down. That cost a full
   rebuild on 2026-08-30.
2. **`crypto key generate rsa` re-issued for switches** — the RSA key is not
   in a running config either.

**A golden IS a captured running config**, so it has both blind spots
identically. Swapping the source changes only *which capture gets
sanitised*.

### The corrected risk

Not *"Oxidized is the wrong store"* but **"its copy may be newer than the
approved one"**, so a redeploy can bake in a change nobody approved. **A
freshness question, not a source question** — which makes the work a
**comparison rather than a migration**, and leaves the sanitizer's two
compensations exactly where they belong.

### How I got there, since the shape recurs

I reasoned from *"the source of truth should be the source"* — a principle
this project does hold — without reading the thing that would have said it
does not apply. **And I had said one turn earlier that I had not read the
script**, then produced a full assessment of it anyway.

The tell was available and is the Stage 2 one verbatim: **every piece of
evidence came from one artifact and the conclusion was about another.** An
assessment whose central claim is about a shell script, built entirely from
this repository.

What the reading cost to obtain: one paste. What the wrong version would
have cost: a migration that reintroduces the 2026-08-30 rebuild.

### What the comparison is, precisely

**Content, with time as context.** *"Newer"* alone fires constantly and
means nothing — Oxidized polls, so its copy is newer than the golden most of
the time, including right after an approved save. The finding is that the
**content differs**; the timestamp then says which way, and only
*differs + Oxidized newer* is *"a change nobody approved"*.

`roundtrip.configs_equivalent()` is the comparator — section-aware over
`strip_for_diff`, the same function a restore baseline is measured with,
which is the right precedent: both ask *"is this device's state the approved
one"*.

### Where it belongs: both, and they are not the same check

* **The sanitizer's pre-write gate** is the one that matters — the last
  moment before an unapproved state becomes **durable**. It must refuse per
  device and name what differs. **And it needs an explicit authorisation
  path**, because the legitimate case is real (an approved change whose
  golden is not saved yet) and a gate with no way through teaches operators
  to disable it — which is how the drift checker came to be off for 24 days.
  `authorise_retry()` is the precedent.
* **The Monitoring signal** answers *"is the fleet diverging"* continuously.
  A report, not a gate. Its value is **timing**: the gate discovers
  divergence when somebody is already preparing a redeploy; the signal
  discovers it when the person who caused it still remembers what they did.

Neither alone: gate-only leaves divergence invisible until a sync, and
signal-only would have shown the s1/s2 VLAN loss **and still let the
redeploy persist it**.

## The third blind spot, measured: a correct omission that had been reported as drift

Asked in both directions before deciding either.

### Does anything depend on the certificate surviving a rebuild?

| | r1–r5 | s1–s4 |
|---|---|---|
| `restconf` + `ip http secure-server` | **yes** — uses the certificate | no |
| yang-push / telemetry | r1–r4, over **NETCONF/SSH** — no certificate | no |
| `crypto pki trustpoint` | 3 each | none |

**It must exist and it need not survive.** RESTCONF needs *a* certificate;
the device makes a fresh one every boot; the yang-push subscriptions ride
SSH; and nothing in this stack pins one. So the sanitizer dropping the
blocks is a **correct omission, not a blind spot** — which was the
possibility worth checking rather than assuming.

### Does the drift comparison report it?

**Yes.** Measured through `configs_equivalent()` with a regenerated body and
a new chassis-derived trustpoint name: **three `only_left` and three
`only_right` lines**, with nothing in the configuration changed by anyone.
`strip_for_diff` keeps both the header and the body; `strip_for_roundtrip`
already removed them, so only the **drift** path carried it.

So every C8000v has held a standing, unexplained difference since the
2026-09-22 redeploy — r1, r2 and r4 logged *"yang-infra: ERROR: Failed to
create a new self-signed trustpoint"*, and commit `758d1f56`'s **only**
changes were certificates.

**Nobody noticed because the drift checker has been off since 2026-08-30** —
switched off three minutes after a run that flagged all nine devices. The
same shape as the others, and this one was *waiting* rather than acting:
re-enabling the checker would have flagged every C8000v for something
correct, **which is precisely the condition that silenced it last time.**

That is why it is fixed before the freshness comparison rather than beside
it. The new comparison uses the same `configs_equivalent()`, so without this
it would have reported every C8000v as divergent on its first run — a
brand-new check whose first act is to cry wolf about a certificate.

### The filter is narrow on purpose

`normalize.strip_self_signed_certs()` removes only
`crypto pki trustpoint|certificate chain TP-self-signed-<digits>` and its
indented body. **A CA-signed trustpoint is configuration somebody chose**,
and a change to it is real drift — asserted, with a control that broadening
the pattern to every trustpoint fails.

Block-aware, because `_strip()` matches line prefixes and a certificate
chain is a stanza. It is a **fifth filter job** in a module whose header
already says the filters are not one list.

## A latent defect whose surfacing would have reproduced its own cause

The certificate finding's third face, and the most transferable thing from
this stage.

**The drift checker was switched off on 2026-08-30, three minutes after a
run that flagged all nine devices** against ad-hoc, stale goldens. Correct
then. The reason was fixed weeks later and nothing anywhere prompted a
re-evaluation — the state file recorded neither who switched it off nor why,
which is its own recorded finding.

**Turning it back on would have flagged every C8000v again** — this time for
a regenerated self-signed certificate, which is *correct device behaviour*.
Five devices, a wall of red, none of it actionable.

So the defect had a property worth naming on its own:

> **Its surfacing would have reproduced the condition that hid it.**

The checker was silenced by noise. The noise it would have produced on
return was noise of exactly the same kind — many devices, all flagged, for
something nobody did and nobody can fix by changing a config. The most
likely outcome of re-enabling it is that somebody switches it off again, and
the second silencing is harder to undo than the first, because now there is
a precedent and a memory of "we tried that".

### The argument it makes

**Fix a known-noisy check before turning a checker back on, not after.**

The instinct is the other way round: turn it on, see what it says, then
triage. That is right for an *unknown* signal and wrong for a known one. For
a defect you have already measured — and the certificate diff was
measurable, cheaply, from the repository, without touching a device — the
triage has already happened. Shipping the noise anyway spends the checker's
credibility to learn something you know.

And credibility is the scarce thing. A checker is only useful while people
read it; every wall of red that turns out to be correct behaviour teaches
the reader that red does not mean act. **The 24 days the drift checker was
lost were not a technical outage** — the code ran fine when it was
re-enabled. They were a trust outage, and the fix for a trust outage is not
deployed, it is earned back.

### The general form

A latent defect is usually described by what it *does* when it surfaces.
This one is better described by what its surfacing *causes*:

* a check that is noisy in a way that resembles its own last failure;
* a guard whose first action after repair is to refuse something legitimate;
* an alarm whose first firing is a false positive of the kind that got it
  muted.

Each has the same shape — **the repair's first visible act re-creates the
argument against the repair** — and each is worth finding before the switch
is flipped rather than after. The test is cheap to apply: *before
re-enabling something that was switched off, ask what it will say first, and
whether that is the same thing it said last time.*

## The first time a tool we built reported success for work it did not do

r6's startup file was **not copied**. The script printed *"Startup-configs
updated."* and exited **0**. `~/labs/r6/configs/r6.cfg` is still the
397-byte bootstrap artefact: `secret 9` → 0, `password 0` → 1.

Per-lab grouping existed to make exactly this visible, and it was invisible:
no error, no mention of `labs/r6/configs`, and the run reported success for
nine of ten files.

### 1. Why the second destination was never written — measured

**Not the subshell.** `while read … done < <(destinations)` was right about
that class. The cause is one line down:

> **`ssh` reads its stdin to EOF and forwards it to the remote command.**

Inside a `while read` loop, stdin *is* the loop's input. So the first `ssh`
in the body swallowed the rest of the destinations list, `read` hit EOF, and
the loop ended after **one** iteration.

Reproduced locally with `cat` standing in for `ssh`:

```
loop as written          TOTAL ITERATIONS: 1
same loop, stdin denied  TOTAL ITERATIONS: 2
```

**Three `ssh` calls sit inside `while read` loops**, and two of them eat it:

| line | call | effect |
|---|---|---|
| 409 | `printf … \| ssh … "cat > .files"` | **safe** — stdin comes from the pipe |
| 411 | the `cp`/`rsync` | **ate the list** — one destination copied |
| 429 | the per-lab `git commit` | **ate the list** — one lab committed |

And it explains why the *per-device* loops were unaffected: **a `for` loop
expands its list before the body runs**, so nothing in the body can truncate
it. The bug is specific to `while read`, which is the construct I reached
for *because* of the subshell rule — a correct fix for one class sitting
directly on top of another.

### 2. Why the full diff showed nothing — two candidates, one discriminator

The same root cause is available: the `for` loop's `ssh` calls inherit the
**terminal** as stdin while `less` is trying to own it, so `less` can be
handed EOF and quit immediately.

But there is a simpler candidate, and it is not a bug: **the prompt defaults
to No.** `read -r -p "Show the full diff? [y/N]"` followed by
`[[ "$ans" =~ ^[Yy] ]]` means Enter skips the review.

**The discriminator is one question** — what was answered. If `y` and
nothing appeared, it is the tty contention. If Enter, the review step did
nothing *correctly*, and the finding is instead that **the only review step
in a script that overwrites boot configuration is opt-in and one keystroke
from being skipped.**

Worth stating either way: a confirmation whose default is "don't show me"
is not much of a confirmation.

### 3. What makes "copied N of M" checkable rather than reported

The loop's own counter is a **report**. It says what the script believes it
did, and this run proves the belief can be wrong while every command in it
succeeded.

**The check is to read the destinations back**, from the map, before the
staging directory is removed:

* count destinations **before** the loop and refuse unless as many succeeded
  — that catches the truncation directly;
* then, per device, compare the file at `${CFGDIR[$n]}/$n.cfg` against the
  staged copy (`cmp -s`), and **name every device that does not match**.

The second is the one that matters, and it is the principle already applied
twice tonight: *a failed push reports what landed, not what was pushed*, and
`verify_startup_carries_current()` reads the file rather than trusting the
transport's report. **A transport that says "done" is evidence about the
transport.**

### The shape

The script was written to make a per-lab failure visible, and it failed
per-lab **silently** — because the mechanism that truncated the loop was not
a failure at all. Every command returned 0. There was nothing for the error
handling to catch, and the only thing that could have caught it was a count
compared against the map.

*Nothing was overwritten wrongly; the nine received a benign header-only
update and r6 is exactly as it was.* The state is safe and the report was
false, which is the combination this project treats as the worst one.

## A loop that ran the right check fewer times than there were things to check

The operator's formulation, and it names a variety this project had not met:

> The script written to make a per-lab failure visible failed per-lab
> **silently**, because the truncation wasn't a failure — every command
> returned 0, there was nothing for error handling to catch, and only a
> count compared against the map could have seen it. **Not a check that
> verified the wrong thing, but a loop that ran the right check fewer times
> than there were things to check.**

Everything this project has catalogued so far is a *wrong answer*: a gate
that silently opens, an assertion that passes vacuously, a check answering a
different question, a scan with an empty input. Each is one evaluation
producing the wrong verdict.

This is different. Every evaluation was correct. The destination
`labs/lab/configs` really was copied, really was backed up, really did
succeed. **The defect is the cardinality of the loop**, and no amount of
correctness *inside* the body can see it — the body has no way to know it is
the only iteration.

**So the check has to be outside the loop, and it has to come from the
population** — `total_dests=$(destinations | wc -l)` compared against
`copied_dests`. That is the same structure as the drift checker's
*"checked 7 of 9"* and `--reconcile`'s three buckets: **count the population
independently, then account for every member.** Here the thing being counted
is iterations rather than devices, which is why it did not look like the
same rule.

### The cause, and why `-n` is not the whole fix

`ssh` reads stdin to EOF and forwards it. Inside `while read`, stdin *is*
the loop's input. `ssh -n` on every call not fed by a pipe is the cause
fixed; the count is the **class** caught. Measured against the real loop
text with a stub `ssh` that consumes stdin unless `-n` is passed:

```
fixed form      2 destinations, 2 copied   COUNT ASSERT WOULD PASS
old form        2 destinations, 1 copied   COUNT ASSERT WOULD REFUSE
```

The second line is the point: **with the count in place, reverting the `-n`
fix is caught rather than silent.** A cause fix that only works while
somebody remembers it is a cause fix that will stop working.

### And then read the destinations back

The count says the loop ran the right number of times. It says nothing about
what arrived. `cmp -s` per device against the staged copy, naming every
mismatch, before `STAGE` is removed — the same rule as *a failed push
reports what **landed***, and as `verify_startup_carries_current()` reading
the file rather than trusting the transport's report.

**A transport that says "done" is evidence about the transport.**

### The review is no longer opt-in

`Show the full diff? [y/N]` was one keystroke from being skipped before a
script that overwrites boot configuration. The diff is now **shown**, and
the only question is whether to proceed.

Chosen over "keep the prompt, default to yes" because that still asks
whether to *review*, and there is no good answer to that question — nobody
should be deciding, at 2am, whether to look at what they are about to
overwrite. Removing it leaves one decision, and it is the one that matters.
The pager already handles a long diff, `--yes` still skips everything for
cron, and `--no-deploy` still stops before the clab VM is touched.

## Two loose ends after phase 1 closed, both diagnosed rather than patched

r6's startup file is the sanitised 74 lines, `secret 9` present, `password 0`
absent, and `nmas-check-startup-applies` reads **SAFE** naming
`labs/r6/patches/c8000v-launch-adopted.py@e483dd2475b5` — **r6's own patch,
not the default lab's**, which is the map resolving correctly through the
whole chain. The count and the `cmp -s` read-back both fired: 10 of 10.

### 1. The full diff, failing for a third reason

**The block is correct.** Extracted verbatim from the shipped file and run
against a stub `ssh` that emits a diff for r6 only: the header prints, the
diff prints, exit 0. So the loop, the `-n`, the `$(…)` capture and the
`[ -n "$out" ]` guard are all fine.

What is left is the pager, and that is the finding rather than the bug:

> **The only review step before an irreversible write is piped through an
> external program and two environment variables, and when any of them is
> not what the script assumed, the review silently does not happen.**

`${PAGER:-less -R}` depends on: `less` being installed, `$PAGER` being unset
or usable, and `$LESS` not containing `-F` (quit-if-one-screen, which is a
very common setting and would flash ~60 lines past and return instantly).
Three ways to lose the review, none of which produce an error the operator
would notice among the summary lines.

**Discriminator, one command on the NMAS:**

```bash
command -v less; echo "PAGER=[${PAGER-unset}] LESS=[${LESS-unset}]"
```

* `less` absent → "command not found", the left side writes to a broken
  pipe, output discarded. Straight to the prompt.
* `LESS` containing `-F` → displayed and exited instantly.
* `PAGER` set to something that does not display → the same.

**The fix is to remove the dependency, not to harden it.** Write the diff to
stdout. The terminal has scrollback; the operator asked for the review by
running the script; and a review step that an unset environment variable can
defeat is not a review step. **This section has now failed three times for
three different reasons** — opt-in default, `ssh` eating the tty, and the
pager — which is the argument for it having no moving parts at all.

### 2. The git commit has never worked

**Reproduced exactly.** With a repo at `labs/lab`, `configs/` tracked and
unchanged, and untracked `configs.bak-*` directories present:

```
On branch master
Untracked files:
	configs.bak-20260801-120000/
	configs.bak-20260815-120000/
	configs.bak-20260924-105059/

nothing added to commit but untracked files present
Not a git repo, or nothing to commit: labs/lab/configs
```

That is the observed output, including the status listing "in between".

**So the chain is settled:** `git rev-parse --git-dir` **succeeded** — there
*is* a repo — `git add -A configs` staged **nothing**, and `git commit -q`
failed. `-q` suppresses the *success* message and not the failure
explanation, which is where the untracked list comes from.

**`|| echo "Not a git repo, or nothing to commit"` names two causes and
distinguishes neither**, which is why this has been printing the same line
since August while meaning only one of them. The message is what hid it —
another *reported and never true*, and the reporting is the defect as much as
the cause.

Two sub-cases remain, and one command tells them apart:

```bash
ssh dmarchak@10.0.0.210 'cd labs/lab && git rev-parse --show-toplevel && \
  git check-ignore -v configs; git status --short configs | head'
```

* **`configs/` ignored** → `check-ignore` names the rule. Then `git add -A`
  stages nothing by design and always has.
* **`configs/` tracked and unchanged** → `status --short` is empty. The nine
  received a header-only change whose `! rN - from Oxidized HEAD <sha>` line
  is identical when the Oxidized SHA has not moved, so the files really are
  byte-identical and there is genuinely nothing to commit.

**Did the original single-destination version work?** No — and this is
checkable rather than inferred: for the `labs/lab` destination the new
command is **byte-identical to the old one** with `$dir` substituted for
`$REMOTE_DIR`, same `cd`, same pathspec, same `||`. The per-lab change did
not introduce this. **29 untracked backup directories going back to August
are a repo that has received nothing from this script**, and they are
exactly what a working commit would have made unnecessary: history instead
of copies.

`labs/r6` is the second destination and is probably not a repo at all, which
produces the **same message with no status output** — the two sub-cases
side by side in one run, indistinguishable by the line that reports them.

## Three outcomes, one sentence — and a fourth cause I have not found

### The commit reporting, fixed

Measured on the clab host: `labs/lab` **is** a repo, `configs/` is **not**
ignored, and `git status --short configs` is **empty** — the nine files are
tracked and byte-identical to HEAD, so that commit is a **correct no-op**
(the header's `! rN - from Oxidized HEAD <sha>` line does not move when the
Oxidized SHA does not). `labs/r6` is **not a repo at all**.

**Two genuinely different states, reported with the same sentence.** The
census's missing-baseline exit code again: outcomes of different severity
sharing a report, where one is the system working and the other is a gap in
coverage.

Split into outcomes that can be told apart, each reproduced against a real
git repo:

```
labs/lab/configs: committed
labs/r6/configs:  unchanged - nothing to commit (the content did not move)
labs/r6/configs:  NOT VERSIONED - the parent directory is not a git repo
```

plus `commit FAILED (<reason>)` and `NOT VERSIONED - git add refused
(ignored path?)`, which is the branch that *would* have fired had
`check-ignore` found a rule. **Only `NOT VERSIONED` needs action**, and the
run ends by naming those destinations with the exact `git init` line to
paste.

### The full diff: a fourth cause, and I do not know what it is

Ruled out, each by measurement rather than by argument:

| candidate | evidence |
|---|---|
| opt-in prompt defaulting to No | removed; the prompt is gone and the diff is shown |
| `ssh` eating the tty `less` needs | `-n` on every non-piped call; ten checked by parsing |
| the block itself | extracted verbatim, run against a stub `ssh`: prints correctly |
| `less` missing / `$PAGER` / `$LESS=-F` | `/usr/bin/less`, both unset |
| `less` misbehaving on a terminal | run under a **pty**: paged, showed r6's diff, waited for a key |

That is five, and the section has failed four times. **I do not know the
fourth cause, and I am not going to name a sixth candidate** — that is
exactly the pattern-matching failure that cost an hour earlier tonight, when
a shape that had been right four times was wrong on the fifth.

**The discriminator is one word**, and it separates "the loop produced
nothing" from "the pager ate it" definitively:

```bash
PAGER=cat ./oxidized-to-config.sh      # then answer N at the prompt
```

* diff appears → the loop is fine and the pager is the problem;
* nothing appears → **the loop produced no bytes**, and the cause is in the
  `ssh`/`diff`, not the pager — which would be surprising, because the
  summary loop twenty lines earlier got a real diff for r6 from the same
  command with only `2>&1` instead of `2>/dev/null`.

**Removing the pager is still right and still not a substitute for finding
this.** A section that has failed silently four times could fail a fifth
after the change, and the change would have removed the evidence.

### Should `~/labs/r6` be a repo, and what shape

**Yes — and per-lab, not one repo at `~/labs`.**

The tempting answer is one repo at `~/labs` covering every lab: one history,
one place to look, and a future device in its own lab is covered without
anybody doing anything. **`~/labs/lab` is already a repo**, so that shape
needs its history moved up a level — a migration and a rewrite, against a
store whose whole value is being the record.

Per-lab is `git init` plus a first commit, consistent with what exists, and
no migration. **Its failure mode is precisely what just happened**: somebody
adds a lab and forgets, and the destination is unversioned while the run
reports the same sentence as a healthy one.

So the shape matters less than the coverage check, and the coverage check is
what makes per-lab safe: **the map already knows every destination**, so the
script now names every one that is not versioned, every run, with the
command to fix it. That turns "per-lab repos" from a thing somebody must
remember into a thing the tool reports — which is the same move as the
drift check's *"checked 7 of 9"* and `--reconcile`'s three buckets.

## Four failures, four causes, none of them the logic

`PAGER=cat` displayed the diff. So the fourth cause **was** the pager:
`less -R` with `PAGER` and `LESS` both unset and `/usr/bin/less` present
swallowed the output on that machine, while `cat` showed it correctly —
rendering `-! test marker` with `+0/-1`, which is the comparison being right
at the same moment the display was lost.

Not chased further, and the reason is the finding rather than the flag:

> **The only review step before an irreversible write depended on an
> external program behaving, and on this machine it did not.**

The pager is gone. The diff goes to stdout and the terminal's scrollback
does the job — a pager that cannot be misconfigured into showing nothing.

### The tally is the point

| # | cause | was the logic wrong? |
|---|---|---|
| 1 | the prompt was opt-in and defaulted to No | no |
| 2 | `ssh` consumed the tty `less` needed | no |
| 3 | *(the same run — the `-n` fix addressed 2, not this)* | no |
| 4 | `less` itself swallowed the output | no |

**Four failures of one section, four different causes, and the loop, the
`diff` and the comparison were correct every single time.** Everything that
broke was between the correct answer and the operator's eyes.

That is worth separating from the rest of tonight's catalogue. The other
findings are wrong answers — a gate that opens, a check answering a
different question, a loop running too few times. **This one produced the
right answer four times and failed to deliver it four times**, which is a
different axis entirely: not *is the computation correct* but *does it
survive the trip to the reader*.

And it argues something about where dependencies belong. A pipeline into
`$PAGER` is three dependencies — the binary, `$PAGER`, `$LESS` — in the one
place with no fallback and no error path, guarding the one action that
cannot be undone. **Put the moving parts where a failure is visible, and
none where a failure is silence.**

### What the measurement cost, and what it bought

Five candidates were ruled out here by measurement — including running the
block under a pty, which reproduced `less` paging correctly on *this*
machine and therefore did **not** clear `less` on theirs. That is the limit
of a local reproduction: it can show a thing works somewhere, never that it
works there.

The discriminator that settled it was one word in front of the command, and
it was available from the first report. **A section that fails silently
should be met with the cheapest question that halves the space, not with the
most likely explanation** — the most likely explanation was wrong three
times running.

## A private key in git, from a message that told you what to do and not how

`clab-r6/.tls/ca/ca.key` and `clab-r6/.state.clab.yaml` were committed,
because the *"NOT VERSIONED"* message printed:

```
git init && git add -A && git commit -m initial
```

**The script's own add was already scoped and was fine.**
`git add -A "$(basename "$dir")"` stages `configs` and nothing else — that
line is correct and has been throughout. The bare `git add -A` existed only
in the **recipe the script printed**, and a lab directory holds
containerlab's runtime state beside the configs.

So the defect was in the **advice**, not in the action — which is a shape
worth naming on its own:

> **A message that tells you to do a thing without telling you how to do it
> right is a message that produces the wrong thing.** It is the same class
> as a refusal naming two causes, or an advisory that reads as a blocker:
> the output is the interface, and an incomplete instruction is a defect in
> it.

And it is sharper here than usual, because the message was added **in the
commit that fixed the reporting** — written to close a coverage gap, and it
opened a secrets one. The gap it reported was real; the remedy it offered
was not checked to the same standard as the code around it.

### The recipe now, and it is verified rather than asserted

```
ssh <clab> "cd 'labs/r6' && git init -q && \
  printf '%s\n' 'clab-*/' '*.bak-*/' > .gitignore && \
  git add .gitignore 'configs' && \
  git commit -q -m 'initial: configs only'"
```

An **allowlist**: `.gitignore` first, then the named paths. Never `-A` at
the top of a lab directory. Run verbatim against a directory holding a
planted `clab-r6/.tls/ca/ca.key` and `clab-r6/.state.clab.yaml`, the
resulting repo tracks exactly `.gitignore` and `configs/r6.cfg`.

The message also now says **why**, naming the key, so the next person to
simplify it has the reason in front of them.

### Remediation, and its limit

One commit, no remote: `rm -rf .git` and redo with the recipe above is a
complete removal — the key never left the host, and this project's usual
rule (*"tightening a mode does not undo exposure; rotation is what makes
past exposure moot"*) applies to exposure, and there was none. Containerlab
regenerates that CA per lab deployment, so its blast radius is one
throwaway lab even if it had leaked.

**What would change that answer**: if the repo had ever had a remote, or
been included in a backup, deleting `.git` removes the copy you can see and
not the ones you cannot.

### `labs/lab` was checked, and is clean

`~/labs/lab` has been a repo since before August, and if a human had ever run
an unscoped `git add -A` there, `clab-lab/.tls/ca/ca.key` would be in that
history — **not** an `rm -rf .git` fix, because that repo holds the nine
devices' config history worth keeping.

Measured: it tracks **only `configs`**, and `git log --all --name-only` finds
no `.key`, no `.tls/`, no `.state`. **Nothing to rewrite.**

Two things follow. The worry was unfounded, and **a null result from a
question that could have been expensive is a result** — the alternative was
not "no problem", it was "no answer". And it settled r6's shape by reading
rather than by invention: r6's repo now tracks `.gitignore` and
`configs/r6.cfg`, matching what was already there instead of the `.gitignore`
I had guessed at.

## Doubting a correct report

The *"unchanged - nothing to commit"* line was **right**, and was read as a
failure. The initial commit captured `configs/r6.cfg` after an earlier run
had already removed the marker, so restoring it was genuinely a no-op.

Worth recording because it is the cost of the night's other findings: after
enough reports turn out to be false, a true one reads as another. The defence
is the same one that produced the split — **make the true report say
something a false one could not.** *"unchanged - nothing to commit (the
content did not move)"* is a claim with a mechanism in it; *"nothing to
commit"* on its own is a shrug, and a shrug is what you distrust.

## Phase 1 closed — and both closing findings are about the shape of a message

r6 is onboarded by the wizard, rotated, captured, in NetBox, in the
inventory, in the break-glass record, its platform template approved against
six, its startup file verified **SAFE naming its own launch patch**, and its
lab versioned. `docs/R6_PHASE1.md` carries the state.

The last stretch produced two findings, and neither is about whether a
message was **true**:

### 1. An incomplete instruction is a defect in the interface

> **A message that tells you to do a thing without telling you how to do it
> right is a message that produces the wrong thing. The output is the
> interface, and an incomplete instruction is a defect in it.**

`NOT VERSIONED` printed `git init && git add -A && git commit`, and a lab
directory holds containerlab runtime state beside the configs — so it
committed a private key. Every word of the message was accurate. The gap it
reported was real, the destination it named was right, and following it
exactly produced the wrong repository.

**And it shipped in the commit that fixed the reporting.** The reporting
split was held to the usual standard — four outcomes, each reproduced
against a real repo. The remedy printed beside it was not tested at all. A
fix and its instructions went out together and only one of them was
evidence.

That is the generalisable part: **the advice a tool gives is code that runs
on a human**, and it deserves the same treatment — an allowlist rather than
a catch-all, a stated reason, and a run to confirm it does what it says. The
recipe now writes `.gitignore` first, names the paths it stages, says which
key an unscoped add would have taken, and was verified against a directory
with one planted in it.

### 2. Make a true report say something a false one could not

> **A shrug is what you learn to distrust.**

The `unchanged - nothing to commit` line was correct — the initial commit
captured the file after an earlier run had already removed the marker, so
restoring it really was a no-op — and it was read as another failure. After
a night of reports that turned out to be false, a true one arrives with no
credit.

The defence is not to be more emphatic. It is to **carry the mechanism**:
*"unchanged — the content did not move"* is a claim that a broken path could
not have produced, because it names *why* there was nothing to do.
*"Nothing to commit"* is compatible with success, with a wrong directory,
with an ignored path, and with never having looked — which is exactly why it
earns no belief.

Same principle as every other correction in this stage, turned on the
success case rather than the failure: `inconclusive` rather than `failed`,
*"checked 7 of 9"* rather than a number that reads as complete, *"this is
not the same as none being pending"* — and now **a success that says what it
measured**, so it can be told apart from a shrug.


## A rule is applied to things that have names

The rule was written down, agreed, and enforced. It removed 140 lines. And
the same violation, one expression wide, sat twenty lines away and survived
it for months.

**The rule:** *importing observed state into the source of truth is the wrong
direction.* It is why `netbox_client._scan_device` was deleted — an SSH
scanner that learned a device's configuration by asking the device, when the
golden config was the right source. 140 lines, a docstring, a name. It was
found, argued about, and removed, and the reasoning was recorded so it would
not come back.

**What survived it**, in the same file, in the argument list of the call the
sync makes for every device:

```python
status="active" if (status_cache or {}).get(result["ip"], False) else "offline",
```

`status_cache` is the in-memory ping cache. That expression takes a liveness
observation — whether one ICMP or TCP attempt answered within five seconds —
and writes it into the source of truth as a standing claim. It is the rule's
own example, in miniature, and nobody looked at it, including me, for as long
as it has existed.

### Why it escaped

Not because it was hidden. It is on one line, in a file that has been read
closely and edited repeatedly this month, in a payload every reviewer of the
NetBox work has scrolled past.

It escaped because **a rule gets applied to things that present themselves as
subjects for a rule.** `_scan_device` had a name, a signature, a docstring and
a line count. You can ask "should this function exist?" and the question has
somewhere to land. `status=` inside a call is not a subject; it is a detail of
a call whose subject is `_upsert_device`. Reviewing the call means asking
whether the *device upsert* is right. The argument goes past as punctuation.

The generalisation, which is what makes this worth its own entry: **the unit
a rule is enforced against is the unit the codebase makes nameable.**
Functions, modules, files and classes get audited because they can be listed.
Expressions, arguments, dictionary literals and default values do not get
listed, so they are never the thing an audit is *about* — they are only ever
visible as part of something larger, and if that larger thing is fine, they
inherit its verdict.

This is the same shape as three failures already recorded here, and naming it
ties them together:

- a docstring that names the *ordering* as a source, because prose is not a
  subject for a test
- a rule living in one file's docstring and another file's omission, which
  nothing would notice being broken
- `next_ts`, a field written and read by nothing, because a key is not a unit
  anybody audits

### The method that finds the rest

Not "read the file again". The defect is invisible to reading precisely
because it is not what reading is organised around.

**Parse for the unit the rule is about, not for the unit the language is
organised into.** The rule here is about *fields written into NetBox*, so the
subject is a **payload literal**, not a function. So: walk the AST, find every
dict literal that looks like a NetBox payload, and for each key report how its
value is produced — a name, a constant, or an inline expression — and whether
that expression touches anything that smells of observation.

That took about fifteen lines and, on its first run, found **four more fields
carrying observed state**, two of which turned out to be a separate defect
(`comments` and `local_context_data.ndm_sync` both embedded the sync's own
timestamp, so both differed on every sync by construction).

It also corrected the rule while applying it, which is the part I did not
expect. The obvious discriminator — *observed versus intended* — does not
work, because the NetBox import is **designed** to run from golden configs,
and a golden config is an observation. What separates the acceptable cases
from the defect is:

> **does this field change without anybody deciding it?**

`serial`, `model` and `os_version` change when the hardware or the image
changes. A ping result changes on a five-second timer. A sync timestamp
changes *because the sync ran*. Only the last two are the wrong direction, and
the reformulated rule says so where the original did not.

### What it cost, and what it nearly cost

It cost one false statement in the source of truth: NetBox said s1 was offline
while s1 was answering SSH, and nothing would ever have corrected it.

It nearly cost more. The NetBox inventory source filters on `status=active` by
default, so on a NetBox-sourced list the same transient would have removed the
device from the inventory — absent, not skipped, not named — and the next sync
iterates the inventory that no longer contains it. **Self-sealing.** That it
was not firing is down to `default` being a local list, which is luck rather
than design.

And the thing that found it was the modification record, built the day before,
on its first real run. `--compare` said *no object was created or destroyed*
and that was true; the drift checker compares configs, not NetBox fields; the
census compares identity, and an in-place status change alters neither an
object's id nor its display. **Nothing else looks.**


## The s1 arc: six steps, each one only possible because of the last

2026-09-24, one evening. It is the clearest demonstration of the method in
this project, and worth setting out end to end because **no step in it could
have happened on its own**.

### 05:22 — a false statement enters the source of truth

The NetBox sync set device status from `device_status_cache`, the in-memory
ping cache. One ICMP-or-TCP attempt to s1 did not answer within the five
seconds before the sync ran, so NetBox recorded **`status: offline`**.

s1 was up. It answered SSH, and returned its running configuration on request.
The claim was false when it was written, and nothing in the system would ever
have corrected it — `status` was written only by a sync, and the next sync
would have had to catch the same device answering.

### Nothing that existed could see it

Three checks could plausibly have been the one to notice, and each was
**working correctly** while being structurally incapable of it:

- `nmas-netbox-census --compare` says *no object was created or destroyed*,
  and that was **true**. Its identity is `id:display`, and an in-place field
  change alters neither.
- the drift checker compares **device configurations** against golden. NetBox
  fields are not in its population at all.
- the census's tagged-object comparison tracks **membership**, not contents.

This is the shape the project has hit repeatedly: not a check that failed, but
a set of checks whose union had a hole in it that none of them was wrong to
leave.

### Hours earlier, the thing that could see it was built

The modification record — `data/netbox_modified.json`, written by `_nb_patch`
— exists because an update carries **no provenance**: the `nmas-managed` tag
is injected on POST only, correctly, since the tag means *NMAS created this*
and claiming a human's object would make it deletable. So NMAS could modify
anything and leave nothing behind. That gap had been closed that afternoon,
for the 2026-09-24 address incident, in which one IP object was moved between
six devices for weeks with every provenance check passing.

**On its first real run it caught s1**, in a field nobody had thought to
check, on a device nobody had reason to suspect.

### The writer was already forbidden by a rule nobody had applied to it

`netbox_client._scan_device` — 140 lines of SSH scanner — had been **deleted**
under *"importing observed state into the source of truth is the wrong
direction"*. A ping result is observed state. The same violation, one
expression wide, sat in the argument list of the call the sync makes for every
device:

```python
status="active" if (status_cache or {}).get(result["ip"], False) else "offline",
```

It survived the rule because **a rule is applied to things that have names.**
`_scan_device` had a signature, a docstring and a line count; you can ask
*should this function exist?* and the question lands. An argument is not a
subject — reviewing that call means asking whether the device upsert is right,
and the argument goes past as punctuation.

Finding the rest needed a different method: **parse for the unit the rule is
about, not the unit the language is organised into.** Fifteen lines walking
payload literals rather than functions found four more fields carrying
observed state — and corrected the rule while applying it, because *observed
versus intended* does not separate the cases (the import is **designed** to
run from golden configs, and those are observations). What separates them is
**does this field change without anybody deciding it?**

### The correction needed a distinction that only the record made possible

The first repair tool asked *did NMAS create this device* — and answered
**no** for s1, whose cohort was imported five months before provenance existed.
It refused to correct a value it had itself written, in a message asserting
the status was *"somebody's decision"*.

*Did NMAS create this object* and *did NMAS write this value* are different
questions, and **the second had been unanswerable until that afternoon**. The
reset takes its authority from the log now, which is also stronger than
resetting to a default: it restores *what the field held before NMAS touched
it* — `active` for s1, and `staged` for a device somebody had deliberately
staged.

Then the same created-object record came back for **the question it actually
answers**. The log holds only updates, so reaching its earliest entry does not
mean reaching an object's origin: r6 had been POSTed `offline` (the ping cache
had not yet seen a device that had just booted) and PATCHed `active` later, so
its one logged `before` was NMAS's own create-time write. Restoring it would
have marked a healthy device offline. Creation is now the **existence** test —
*does "before NMAS" name anything* — scoped to the case where the unwind ran
out of log.

### And the restore is in the log

```
06:07:55  s1  before 'offline' → after 'active'
```

The correction is recorded by the same mechanism that found the fault, which
is the property that makes the record worth keeping rather than merely worth
having built.

### What the chain rests on

Every step depended on the one before it. Remove any and the rest do not
happen: no record, no detection; no detection, no sweep; no sweep, the rule
stays unapplied; no rule applied, the writer keeps writing; no
write-versus-create distinction, no safe correction.

And the whole thing rests on something smaller than any of them. **The census
was changed to say which claim it was making** — *no object was created or
destroyed*, explicitly **not** *nothing changed* — with a modifications line
beside it. Had it gone on printing an unqualified `PASS`, the record would
have been written, s1's entry would have been in it, and nobody would have had
any reason to look.

A report that qualifies its own claim is not a courtesy to the reader. It is
the thing that makes the next question askable.


## What P.3 cost and bought (2026-09-26)

P.3 was scoped as five register items (B12, B11, D5, D4, C23) and the cuts:
make every path that changes a device guarded, or gone. It closed those. It
also produced eleven findings nobody had scoped, and every one came from doing
the work, not from looking for it:

- **B13**: the terminal sent the stored enable secret into a session that was
  already privileged, and echoed 27 of s1's 32 password characters to a
  browser. Found by opening the terminal through the tunnel to check the gate.
- **B14**: every device stored its login password twice.
- **B15**: a rotation of that exposed credential completed on the device and
  in the store, and its persistence silently did not run. The boot file kept
  a public password.
- **B16**: an ungated GET ran any exec-mode command. Found because the gate
  table, keyed on HTTP method, covered eighteen routes and not the
  nineteenth.
- **C24, C27, C29, C31, D10, D12**. The last was the terminal: one shell per
  device, shared by every browser that opened it.
- **C28**: four settings erased on 2026-09-23, each rediscovered by the
  failure it caused.

The shapes: gating eighteen routes and opening the nineteenth; routing two
buttons into a preview nobody had examined; surveying for one thing and
noticing another. **Gating a path is not reviewing it.**

**Item 2 of the acceptance, observed on the host by the operator.** A real
deploy through the tunnel, and both commits verified through the gate:

    c7711d6 golden: baseline 1 device(s) via pipeline batch-85f32b   Actor: dustnm@gmail.com   Verified: access
    2fb07db host_vars: r1 TEST ACTOR FIX 8401b88                     Actor: dustnm@gmail.com   Verified: access

Two different paths, the intent commit and the deploy's golden. With the
unauthenticated 403s measured at step 9, that is the gate refusing without a
person and passing with one, on the real system.

**Two things the acceptance run is worth keeping for.**

1. **The stale floor.** The plan asked for "at least 131 mutating rules",
   measured before steps 2, 3 and 7 cut eleven routes. Applied as written it
   would have FAILED correct code, reading as a regression. It was caught by
   checking the number against the population rather than against the plan.
   That is the proxy-population rule: a count stands in for "the scan found
   everything", and the population it counts moves. Note the direction. A
   floor set too HIGH fails loudly on correct code. The dangerous direction is
   too LOW: a floor that passes because the population shrank under it. Both
   are the same mistake, a number that has stopped describing its population.
2. **The controls.** There were eleven. Each removed the property its item
   protects, and each failed the test aimed at it with no collection errors,
   so a crash could not pass as a control. Every file was restored from a
   scratch copy, a rule written the day before, after a `git checkout`
   restore reverted a step's uncommitted work. The rule earned itself within
   a day.
