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
