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
