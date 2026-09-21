# Changelog

All notable changes to Agentic NMAS.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
NSoT phases refer to [docs/NSOT_PLAN.md](NSOT_PLAN.md).

---

## [Unreleased] — Multi-network correctness, and secrets stop leaving the host

### Fixed — template secrets collided across device lists (audit A)

The credential-store key was `<hostname>:<ref>` in one installation-wide file,
built by four f-strings in three modules. Two lists each holding an `r1` shared
a key; the second extraction silently replaced the first, and the first network
then deployed the second's SNMP community with every deploy guard satisfied.

- `credentials.template_secret_key()` is the one construction site
  (`<list-slug>:<hostname>:<ref>`); a grep test allows only its own body.
- `set_template_secret()` records the owning list and refuses a cross-list
  overwrite. A list updating its own secret still works.
- `migrate_template_secrets_to_list_scope()` runs at startup, idempotent.
- `assert_no_secret_values()` deliberately scans **every** list, narrowed only
  by device: scoping it by list made a wrong derivation check nothing.

### Fixed — the deploy path asked a global which network it was writing to (audit B)

`PipelineContext.list_name` is set once by the originating request. The pipeline
called `get_current_list_name()` at three points after the push, including the
golden commit; that function reads a file on disk, so switching lists during a
45–90s convergence window committed one network's captures into another's repo.
`allow_new=False` hid it until two networks shared a device name or address.

### Fixed — restore read its inventory from the active list (audit C)

`plan_restore()` and `build_targets()` took `list_name`, used it for the repo,
and read devices from `get_current_device_list()`. Now `_devices_of(list_name)`.

### Added — secrets are redacted at the provider boundary (audit D1)

`modules/redact.py`, applied to `system`, `messages` and `tools` immediately
before `messages.create()`. Nothing was masked on any outbound path before
this, and the AI read-first workflow loads golden configs into prompts — so the
plaintext router passwords and every SNMP community had very likely already
left the host. Redaction is at the boundary rather than at each reader because
`show running-config`, backups, drift diffs and free-form commands carry the
same values. Values become `<redacted:<ref>>`; values under 8 characters are
left alone.

---

## [Unreleased] — The round-trip metric could not see nesting depth

### Fixed — BGP address-families were flattened by parse, render, and the metric

`roundtrip._sections()` was built on `split_blocks()`, which appends every
indented line to one list regardless of depth, so a two-level block compared as
one level. `cisco_iosxe/base.j2` hoisted every BGP network and neighbor
activation out of its address-family to the top of `router bgp`, and scored
**100%** — on the three devices whose configs the comparison least understood.

`merge_commands()`, which decides what goes on the wire, has been depth-aware
since Phase 3c and would have sent 7 spurious lines for r3/r4 and 14 for r5,
including an IPv6 prefix outside `address-family ipv6`. The tool could compute
the right answer and simultaneously report there was nothing to compute.

The fixtures carried BGP address-families all along; parse and render flattened
symmetrically, so both sides agreed with each other while both disagreed with
the device. The existing `test_bgp_address_families_on_r3_r4_r5` asserted
`any("address-family" in s for s in bgp["settings"])` — it pinned the
flattening as correct, under a name that made the construct look covered.

- `modules/nsot/sections.py` — the indentation→ancestry algorithm, alone.
- `_sections()` keys on a line's full container path.
- `section_is_unordered()` tests every path component; order-significant wins.
- `routing.bgp.address_families` is `[{afi, networks, neighbors, settings}]`.
- `scripts/nsot_metric_diff.py` — flat vs depth-aware, per device, plus every
  nested construct in the corpus. The two now agree everywhere.

Two regressions the stricter metric introduced, both caught and pinned: the
global scope was counted as a section (unknown config scored 16.7%, not 0) and
compared as ordered (every device reported one reordered section named `""`).

### Fixed — approval hashed only `base.j2`, not the macros it imports

Found while landing the above: editing `templates/_common.j2` — the routing,
interface and service macros for **both** platforms — would have left
`cisco_ios/base.j2` approved for s1–s4. The fingerprint now covers the whole
import closure, path-labelled. Editing any file revokes every approval whose
closure contains it.

### Changed — revocation is a recorded finding

`approval.revoke()` requires a reason and writes a tombstone instead of deleting
the record. `is_approved()` refuses a revoked record **first**, ahead of the
scheme and fingerprint checks: a decision recorded by a person must not be
overturnable by a computation that runs afterwards.
`POST /templates/revoke/<path>` makes it reachable.

### Live

- `cisco_iosxe/base.j2` revoked (`14e61b8`) naming the defect; verified no harm
  reached a device — every deploy in repo history touched only r2/s3/s4 and
  changed only loopback descriptions.
- Shared macro fixed in the repo (`c8e07cc`), both approvals revoked by closure,
  both re-approved (`9cebd59`) with all nine devices at 100%.
- r1, r3, r4, r5, s1, s2 onboarded; all nine now have committed intent, resolvable
  secrets, an approved template, and **zero commands to send**.
- Save All: one commit `7f5b0f5`, `baseline/20260921T033554Z`, nine devices.

---

## [Unreleased] — Restore, item 2: intent moves with the device

### Fixed — `_deploy_one()` was deleted and the suite did not notice

Removed in `061158c` by a slice edit that replaced from `_baseline_earned` to
the end of the file; `_deploy_one` sat after it. It is the only function in
`routes/deploy.py` that opens a connection, and it was live on the NMAS for
three commits. 1133 tests passed throughout, because every test exercises the
pieces it calls and nothing calls it.

Recovered from `da8d7d4`. `test_deploy_contract.py` now parses each route
module's AST and asserts every private name it calls is defined — it fails in
0.1s with the function removed.

### Added — committed intent is restored with the device

* `_write_restored_intent()` writes the ref's `host_vars` forward for devices
  whose restore **succeeded**, in the **same commit** as their golden capture.
  A device that failed keeps today's intent.
* The ref's YAML is re-committed **verbatim**, not re-serialised from the
  parsed dict. That needed `repo.git_raw()` — `git()` strips stdout, which
  dropped the trailing newline and produced a one-byte diff labelled "restore".
* Staged to `.nsot/staging/restored_intent/` across the crash window.
* `validate_restored_intent()` refuses at plan time when a ref's intent no
  longer round-trips through today's templates, or names a secret the
  credential store no longer holds.
* **Un-onboarding is opt-in.** A device the ref predates is skipped by default;
  removing its committed intent requires ticking it, and re-runs the preview so
  the operator confirms an actual command list.
* `RestoreTarget` gained `ref_intent`, `ref_intent_text`, `un_onboard`.
* `RefSource` for restore declares `("golden/", "host_vars/")` — never
  `templates/`, `bindings.yml` or `.approvals.json`.

### Changed — a baseline tag is earned by measurement on the restore path

> A skipped device counts only if it was **measured**.

* Restore now requires **every inventory device measured equivalent to the
  ref**, whatever path got it there.
* `_measure_unchanged()` reads back a device that needed no commands, so
  "nothing to change" becomes a measurement instead of an inference drawn from
  a stored capture. A failed read contributes nothing and declines the tag.
* Residue therefore denies a restore baseline — merge-only cannot remove it, so
  the network is not at the ref, and the tag says so.
* Deploy baselines are unchanged: coverage, not content.

### Fixed — `save_golden()`'s empty-commit guard ignored `extra_paths`

A restore to a ref a device already matches changes no golden and still moves
that device's intent. The early return left the intent written and uncommitted.
The guard now asks about the whole commit; a call with neither golden changes
nor staged `extra_paths` still creates nothing.

---

## [Unreleased] — Run 2 landed, and the deploy that minted a device

Run 2 succeeded: `1f0140a5`, tag `golden/s4/20260920T231156Z`, verify converged
(OSPF 5→5 neighbours), `write memory` confirmed on the device, golden byte-identical
to what was sent. It also introduced a regression, which is a pointed place for
one to appear.

### Fixed — `save_golden()` minted an identity instead of failing

```python
identity = item.identity or _manifest.new_device_uid()
```

One line. A caller that simply *forgot* to pass an identity got a brand-new
device rather than an error, and stage 8.5 forgot: the inventory row carries a
`device_uid` only if the CSV has one, and s4's did not. The first successful
deploy gave s4 a **second manifest entry**, with an empty platform, for a device
the manifest had known since migration. Verification check 3 — "no duplicate
device entries" — went red.

**A function that creates identity when none is supplied will always mask a
caller that forgot to supply it.** Same shape as intent derived from current
state: the fallback is indistinguishable from the correct answer, so the bug
cannot surface.

Two fixes, deliberately independent:

- `resolve_identity()` takes the item's identity, else the manifest by IP, else
  by name, and mints **only** when `allow_new=True`.
- Stage 8.5 resolves the existing identity from the manifest itself and passes
  it into `GoldenItem`, and calls `save_golden(..., allow_new=False)` — a
  deploy targets a device the inventory already knows.

Minting now happens in exactly one place and only when asked for, so Phase 4's
onboarding wizard does not inherit the trap.

### Changed — `deployable` subsumes sendability

The ASCII guard refused an em dash before connecting, but only *after* the
artifact had already reported `deployable: True`. Two answers to "can this go
out" that disagree is worse than either alone, because the reassuring one comes
first and the operator reads that one.

`build_artifact()` now measures non-printable bytes on the **truthful** render
— never the masked one, since the mask is U+2022 and a masked render is
non-ASCII by construction — and `blocking_reasons` carries them with line
numbers. One answer.

---

## [Unreleased] — Run 2, attempt 3: a corrupted partial write, and the net that did not catch it

The first deploy to reach a device. It left this on S4:

```
interface GigabitEthernet0/1
 description NSoT-managed b        ← intended: NSoT-managed — CSCI 5840 Lab 4
```

### Fixed — nothing checked that a command could be sent

The em dash is U+2014, three UTF-8 bytes. The IOS CLI consumed the first, lost
sync, and discarded the rest of the line. Netmiko could then not match its echo
and raised a *pattern timeout* — an error naming a regex, not a character.

Every guard built to this point validated a command list's **provenance and
identity**: where it came from, that it equalled what was confirmed, that
nothing was synthesised. None asked whether the bytes could be sent.

`assert_sendable()` refuses any command containing a byte outside printable
ASCII (0x20–0x7E), **before connecting**, naming the character, its codepoint
and its column:

```
command 2 of 3 cannot be sent — '—' (U+2014) at column 27.
The IOS CLI accepts printable ASCII only.
```

Guarded at **both** boundaries: `hostvars.assert_printable()` refuses at
commit, so the character never reaches a plan and nobody confirms a list that
cannot be sent; `merge_commands()` refuses before connecting, because a value
an operator types needs a guard where the typing happens *and* where the
sending happens.

### Fixed — rollback did not fire on a mid-push failure

Two independent bugs, both excluding exactly the case rollback exists for.

**The trigger** required `"deploy" in self.ctx.stages_completed` — false
precisely when the deploy stage is the thing that failed. It now fires whenever
a push was *attempted*, which is what `push_results` being non-empty means.

**The target list** was `push_results` filtered to `ok` — so a device whose
push died mid-stream was excluded, though a partial push is the state most in
need of restoring. It is now every device not explicitly skipped.

Together: a push that failed halfway rolled back nothing, which is what
happened on S4.

### Added — a failed push reports what actually landed

`send_config_set` raising means something was **already sent**. Reporting only
"the push failed" conflates that with "the device is unchanged", and the
difference is the entire question an operator has afterwards. The corruption on
S4 was found by a human going to look, with the pipeline's own connection still
open.

`_capture_failure_state()` reads each attempted device back and diffs it
against the pre-change snapshot, recording `landed`, `lost` and
`device_changed`. It runs **before** rollback, so the repair does not destroy
the evidence, and a device it cannot read reports `device_changed: None` —
unknown never reads as unchanged. The deploy result carries it, alongside the
exact `commands` that were sent.

---

## [Unreleased] — The confirmed list is derived, and the seam is tested

### Changed — `rendered_commands` derives from `confirmed_commands`

The pass-through flag added in the previous entry worked, and it was still a
**convention** — and conventions are what failed here twice. `PipelineContext`
now carries `confirmed_commands` (default `None`), and `rendered_commands` is a
property:

- when a confirmed list exists, it is what the property returns
- **assigning over it raises** `ConfirmedCommandsOverwritten`

Stage 2's early return is still the intended path; the assignment at the end of
that function is now refused by the setter as well, so deleting the return
would raise rather than quietly substitute. Same shape as
`RenderArtifact.deployable`: the safe answer wins by construction, not by
everyone remembering to check a flag.

### Added — a test of the handoff, not the stages

Every pipeline test asserted on a stage's *output*. Both wiring failures lived
in the handoff **between** stages: `_deploy_one()` set `rendered_commands` and
stage 2 overwrote it, so the list the plan published and the list that would
have reached the wire were different objects and nothing compared them.

`TestTheConfirmedListReachesTheTransport` runs the full `PipelineRunner` with a
spy in place of `_push_config` and asserts the command list arriving at the
transport equals the list the plan published, by value and by fingerprint.

Both historical bugs were reintroduced to confirm it catches them:

```
with stage 2 re-rendering : 1 failed
with the whole config sent: 5 failed
```

---

## [Unreleased] — Run 2, attempt 2: the pipeline re-rendered over the confirmed list

```
"stage":  "template_render",
"reason": "Unknown config type: 'template'"
```

`_deploy_one()` populates `ctx.rendered_commands` with the exact confirmed
program, then hands the context to `PipelineRunner`. Stage 2 overwrote it
unconditionally — `ctx.rendered_commands = rendered` at the end of the stage —
so the confirmed list was discarded and the stage then failed on a
`config_type` no generator knows.

The failure was the *lucky* outcome. Had `config_type` been a known generator,
stage 2 would have rendered something else and pushed **that**, silently, after
the operator confirmed a different list. The wiring was never correct; an
unrecognised type is the only reason it surfaced as an error rather than as a
wrong deploy.

`PipelineContext.pre_rendered` now marks a caller that has already decided what
to send. Stage 2 passes those through and logs it. Setting the flag with no
commands is refused outright — *"refusing to render a substitute for a list the
operator confirmed"* — rather than falling back to rendering, because a silent
substitution is the failure this whole mechanism exists to prevent.

Stage 2 runs before anything connects, so nothing reached the device.

---

## [Unreleased] — The confirmed program is the sent program

Found on run 2's plan, one step before the push.

```
what the plan showed the operator :   1 line
what the pipeline would send      :  83 lines
```

`_deploy_one()` set `rendered_commands` to the entire rendered config while the
preview showed the merge diff. Confirming "add one description" would have sent
`hostname s4`, `no service password-encryption`, the SNMP community line, and
eighty more.

"IOS treats a re-applied identical line as a no-op" is true, and it is an
argument about blast radius, not correctness. The confirm step makes one claim —
*this is what will happen* — and a push exceeding its preview falsifies that
claim whether or not the excess is harmless.

### Added — `merge_commands()`

`merge_diff()` answers *what differs*; that is not a program. `' description …'`
is an interface sub-command and applies in global configuration mode if sent
alone. `merge_commands()` answers *what to send*:

- each added line preceded by its **full ancestor chain, in order** — a line
  under `address-family ipv4` inside `router bgp 65001` gets both, because a
  partial chain applies it to the wrong address family silently and
  successfully
- one `exit` per open level at the end of each contiguous group, so a
  two-level unwind leaves the next group at the right place; a group whose
  chain is empty emits none, since `exit` from global config leaves config mode
- **never `end`** — it leaves configuration mode, and a list that does so
  part-way through is a different program than the one confirmed

### Added — the equality is enforced at apply

`/deploy/plan` publishes the exact `commands` and a `command_hash`.
`/deploy/apply` **recomputes** the list from current state and compares; a
mismatch refuses that device with *"the device or intent changed since you
confirmed — re-run the preview and confirm the new command list"*, per device
rather than aborting the batch. Same one-shot discipline as the Phase 0 plan
token, applied to the program. Recomputed server-side: a hash the client sends
back proves only what the client saw.

### Fixed — `assert_merge_only()` was vacuous

It checks that every pushed command appears in the intended config. While
`to_push` *was* the intended config, the test was "is every line of X in X" — it
would have passed on any input, forever. It now receives the merge program and
has something to check, with a test that asserts it **raises** on a synthesised
line. `exit` is exempted as mode control, explicitly and by name; `end` is not.

This is the **third** real check found positioned where it could not fail —
after `assert_no_negation` and the two template roots — and is recorded in
`docs/NSOT_WRITEUP_NOTES.md` as a distinct family from the transformation bugs.

---

## [Unreleased] — Run 2, attempt 1: secrets lost between staging and commit

Caught by running it. The deploy refused, correctly, and nothing was pushed.

### Fixed — `to_yaml()` destroyed every `secret_ref` on a second pass

`to_yaml()` strips `secrets` on the way out and recomputes `secret_refs` *from
that key*. Feed its own output back in — which is exactly what read-staged →
write-committed does — and the key is gone, so the refs come back empty:

```
after one pass  : secret_refs:
                  - snmp_community_ro
                  - user_admin_secret
after two passes: secret_refs: []
```

**The existing fixed-point test could not see this.** It runs parse → render →
parse and compares `to_yaml()` of both; both inputs come from the parser and
therefore always carry `secrets`. The *parser* was tested for a fixed point.
The *serialiser* never was — and it is the serialiser that both stores round
trip through.

### Fixed — promotion could never move a secret value into the store

`commit_extraction()` read the staged YAML back and promoted that. But the
staged file carries `secret_refs` and never values, **by design** — so
`store_secrets()` found nothing to move and reported `count: 0` where the
extraction had reported two. The credential store stayed empty.

Secret values exist at exactly one moment: extraction. The commit route now
re-runs the extraction, compares `to_yaml()` of the fresh result against the
reviewed staged file, and **refuses with 409** if they differ — committing
something nobody reviewed is the failure that guard exists to prevent. Only
then does it store the values and write committed intent from the in-memory
extraction.

### What the failure actually looked like

Every layer downstream failed closed, in order:

```
secret_refs: []          →  hydrate_secrets() resolves nothing
                         →  render emits <missing-secret:user_admin_secret>
                         →  assert_no_mask() raises MaskedContentError
                         →  plan reports error, to_add: 0, nothing pushed
```

`<missing-secret:` is in `MASK_MARKERS`, so the backstop written for a
different failure — a masked preview reaching the deploy path — caught this one
too. `intent_drift` reported `adds: 3, removes: 3`: the three secret-bearing
lines, correctly described as drift by a render that was broken.

The stop happened one step before the push, on a read-only plan.

---

## [Unreleased] — Pre-run-2 corrections

### Fixed — the secret check would have refused legitimate commits

The value half of `assert_no_secret_values()` compared by plain substring with a
three-character floor. A stored value of `admin` trips on `username admin
privilege 15` — ordinary configuration, in the field it belongs in, reported as
a leaked secret. That refusal blocks the **entire intent path**, behind an
error that reads like a breach.

Now: an 8-character floor, whole-token matching (so `Secret12` inside
`Secret123456` is a different value, not a leak), and a refusal that names the
line, the field, the secret, and the `secret_ref` to write instead.

The check is **deliberately incomplete** and the docstring says so. A stored
value shorter than the floor cannot be distinguished from ordinary
configuration text; those are covered by the structural `secrets:` refusal and
by the extractor substituting refs at extraction time, not here. A check that
claimed to cover them would be worse than the gap.

### Added — every pushed line is attributed before the confirm

Merge-only pushes every line the render has and the device lacks — not only the
line the operator changed. Anything that drifted on the device since the
capture, or an earlier intent edit never deployed, rides along in the same push.
Merge-only is the right safety property; this is its cost, and the cost has to
be visible before the confirm rather than discovered in the pushed-command list.

`/deploy/plan` now renders the **previous** committed intent against the same
capture and splits `to_add`:

- `from_this_edit` — lines the latest intent commit explains
- `pre_existing` — lines that were already going to be pushed

plus the intent commit sha, subject, and the YAML diff it introduced.
Attribution is **measured, not guessed**. When it cannot be measured — the
first intent commit for a device, an unreadable parent, a template that will
not render — it reports `attributable: false` with a reason rather than
claiming the lines are the operator's.

### Fixed — validation and deploy read different template trees

`build_artifact()` always rendered from `modules/nsot/templates/`, the built-in
seeds, while `approval.validate_template()` rendered from
`config_repo/templates/`, the network's own library. The two are byte-identical
the moment seeding copies them, so nothing looked wrong — and the instant an
operator edits a template, approval validates the edited file and deploy pushes
the seed. **The gate would have been measuring a file the deploy never reads.**

`template_root` is now carried on the artifact, every render inside
`build_artifact()` uses it, and `prepare_device()` prefers the artifact's tree.
A test edits a repo template and asserts the gate sees it while the seeds path
does not.

### Design rule recorded in the plan

Gate on template fidelity, never on intent drift — `docs/NSOT_PLAN.md`, Phase 3
amendment. Template fidelity answers whether the renderer can be trusted for
this device at all; drift is the work, and a gate keyed on the work means no
work can ever be done. Approval stays keyed on capture-parsed host_vars for the
same reason: it is a claim about the template, not about one device's intent.

---

## [Unreleased] — Intent is committed, never inferred

The deploy flow was complete and its effect was structurally zero. With the
approval gate fixed, the first real plan returned:

```
s4: deployable=True approved=True template=cisco_ios/base.j2
   to_add=0  removal_warnings=0  unchanged=82
```

`_artifact_for()` derived host_vars by parsing the device's own captured
config, so intent was a function of current state: the render reproduced the
capture exactly and the diff was empty **by construction**. The same error as
validating a masked render against itself — both sides come from one source, so
the comparison cannot say anything.

### Added — committed intent

- `config_repo/host_vars/<device>.yml` is committed intent and **the only
  intent source on the deploy path**. `.nsot/staging/host_vars/` stays
  gitignored scratch — a proposal, not a decision.
- A device with no committed intent is `bootstrap` and **not deployable**:
  *"no committed intent for this device — review and commit extracted host_vars
  first."* A device whose intent is its current state has nothing to deploy
  toward, and treating the status quo as the goal is how a tool confidently
  pushes nothing and reports success. `bootstrap` blocks through
  `blocking_reasons`, so `deployable` stays a computed property with no backing
  field and no override.
- `POST /templatize/commit/<host>` promotes staged → committed via
  `repo.save_host_vars()`, which has existed and been tested since Phase 2 with
  no caller. Secrets move into the credential store for real here, not as a dry
  run.
- `POST /templatize/committed/<host>` edits committed intent and commits it as
  `host_vars: <device> <summary>`. A summary is required — `host_vars: s4` on
  its own says nothing in a log. **This is how a change is expressed**, not by
  configuring the device and re-extracting.

### Changed — what round-trip validation means

It now measures the template rendered *from committed intent* against the
capture. A difference is not a defect; it is drift, and the three-way
relationship the plan always wanted is visible at last: template, committed
intent, captured reality.

Deployability therefore cannot be judged on that comparison, or every change
would block itself — the difference you intend to push is by definition a
difference between intent and the device. The artifact carries two reports:

| | measured from | used for |
|---|---|---|
| `report` | render of **committed intent** vs capture | drift, informational |
| `template_report` | render of the **capture's own parse** vs capture | template fidelity, **gating** |

Approval stays keyed on capture-parsed host_vars: approval is a statement about
the template reproducing every bound device, so one device's intent edit must
not silently revoke it.

### Masking contract — unchanged, and now enforced at the write

Committed host_vars hold `secret_refs`; the credential store holds values.
`write_committed()` refuses any document carrying a `secrets:` mapping **or** a
resolved value, checked structurally *and* by value — the structural check alone
would miss a value pasted into an unrelated field by a hand edit, which is
exactly what the editor route makes possible. `hydrate_secrets()` is the only
place names become values, in memory, at deploy time; `assert_no_mask()` guards
the other end.

### Fixed — `merge_diff` proposed blank lines as commands

`to_add` included every blank line the render produced, so a device with
nothing to deploy still reported additions and "is there anything to do here"
answered yes for every device, permanently. `!` and `end` were excluded from
removal warnings but not from additions. Both sides are filtered symmetrically
now: a blank line, `!` and `end` are not commands.

---

## [Unreleased] — The deploy gate could never open

Found by running the first real deploy plan, not by any test.

### Fixed — `is_approved()` was asked about one device at a time

`binding_fingerprint()` hashes the **whole bound device set**. That is the
design: onboarding a device must revoke approval, so a device the fingerprint
is not given hashes to the literal string `"unknown"`.

`_artifact_for()` called `approval.is_approved(repo, template, {hostname:
artifact.host_vars})` — one device. For `cisco_ios/base.j2`, bound to s1–s4,
that produced:

```
stored fingerprint : a7c85e85a207c52d
full bound set     : a7c85e85a207c52d -> is_approved True
s4 alone           : 7227fcb19aadcfc4 -> is_approved False
   s1: unknown
   s2: unknown
   s3: unknown
   s4: caae860616f18e6f
```

So **every template bound to more than one device was permanently unapprovable
on the deploy path**, and Phase 3c was unreachable in the normal case. It failed
closed, so nothing unsafe shipped — the flow simply could not run. Same family
as a check that is computed and consumed by nobody: a gate structurally
incapable of returning the answer it is asked for.

`_bound_host_vars()` now builds host_vars for every bound device, cached per
request so a plan over nine devices does not reparse each bound set nine times.
The device being deployed always contributes its own freshly-built host_vars, so
a newer capture cannot be masked by a stale cache entry.

### Fixed — device discovery came from the deprecated store

`_artifact_for()` found the device by scanning `golden_configs/` for a matching
hostname, then fed that IP to `_load_golden_config_file()`. Identity from the
deprecated store, content from the repo. Emptying `golden_configs/` — which the
migration explicitly permits, since it is a read-only fallback — would have
reported "no golden config for this device" for every device that has one.
`_captured_config()` resolves through the manifest first and falls back to the
legacy listing.

### Not fixed — there is no path from an intended change to a render

Reported rather than changed, because closing it is a design decision.

`_artifact_for()` derives host_vars by parsing the device's **captured** config.
Round-trip fidelity is 100%, so the render reproduces the capture exactly and
the merge diff is empty. Verified on the live lab:

```
s4: deployable=True approved=True template=cisco_ios/base.j2
   to_add=0 removal_warnings=0 unchanged=82
```

That is correct behaviour for "deploy the template as it stands". It is also
the only behaviour available, because nothing reads an *edited* host_vars:

- `routes/templatize.py` writes `.nsot/staging/host_vars/` — gitignored — and
  reads it back only for a preview render.
- `repo.save_host_vars()` exists, is tested, and **has no callers**.
- `_artifact_for()` never consults either.

So a per-device change like an interface description has no way to reach a
deployed config. The deploy flow can currently only ever push zero lines.

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
