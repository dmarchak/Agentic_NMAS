# Open findings register

Things measured, recorded, and **not fixed** — with no line item in any stage
of [NSOT_PLAN.md](NSOT_PLAN.md).

**Why this file exists.** Each of these was written into `CLAUDE.md` or a
stage document at the moment it was found, in prose, beside the thing it was
found next to. That is the right place to explain *why* something is true and
the wrong place to keep a list: prose accumulates invisibly, and the only way
to know what is outstanding was to have been present when each one was
recorded. The register is the list; the prose stays where it is and is linked.

**Rules.** An item leaves this file by being fixed, by being scheduled into a
stage, or by being closed with a reason. It does not leave by being
forgotten. Anything recorded as *"not applied"*, *"noted, not yet
addressed"*, *"recorded as a gap"* or *"left open"* belongs here on the same
day it is written.

Status: **open** unless stated. Last reviewed 2026-09-25.

> **C3 is closed (2026-09-25, [PHASE2_DHCP.md](PHASE2_DHCP.md) §23).** The
> recorder did **not** miss the write: `data/netbox_modified.json` holds
> `r1 comments … TEST → …` at `06:34:40Z`, written 0.18 s after NetBox's
> `last_updated`. The silent syncs since the churn fixes stand as evidence
> again. How the entry came to be read as absent was not determined.

---

## A. Data integrity — NetBox

| # | Finding | Kind | Where recorded |
|---|---|---|---|
| A1 | **Nothing backs up NetBox.** `config_repo/` is committed, tagged, pushed and restorable; NetBox is a live database this tool writes to with no history, no baseline and no rollback. The 2026-09-24 damage was bounded *only* because its contents happened to be derivable from golden configs — a property of what was damaged, not a guarantee. Anything hand-curated (a site description, a custom field, a tenant, a rack) has nothing to restore it from. | build | CLAUDE.md, *"git is versioned and NetBox is not"* |
| A2 | **The census records identity, not assignment.** `_identity()` is `id:display`, so an object moved between parents is invisible to `--compare` — which is exactly the 2026-09-24 address incident. The modification record now catches NMAS's own moves; a move by anything else still is not seen. | build | [PHASE2_DHCP.md](PHASE2_DHCP.md) §12 |
| A3 | **Nine of ten devices are outside Remove's provenance.** Both halves — the `nmas-managed` tag and `netbox_created_ids.json` — arrive in Phase 0 (2026-09-20); the sync dates from 2026-04-22. The nine reference devices carry neither, so a provenance-based Remove can act on r6 and is blind to the rest. Safe, and it means the teardown mechanism has never been proven against them and by construction never can be. Adopting them is a deliberate act. | decide, then build | [PHASE2_DHCP.md](PHASE2_DHCP.md) §16 |

## B. Secrets and audit surfaces

| # | Finding | Kind | Where recorded |
|---|---|---|---|
| B1 | **`skipped_drifted` returns a whole device configuration in an API response.** Unredacted, on a JSON route. The diagnostic value was already removed (it now carries both hashes); the config remains. | build | CLAUDE.md, *"A diagnostic that dumps the artefact but not the comparison"* |
| B2 | **A credential rotation leaves no durable record.** `persist()` is reached only from two scripts, and nothing writes an audit file, a run log or anything in `data/`. Whether the Oxidized stages have been failing since the 2026-09-23 settings erasure **is not knowable from the repository**. | build | CLAUDE.md, *"`oxidized_reload` is stage 2"* |
| B3 | **Orphaned credential overrides are reported and never removed.** `nmas-credential-overrides` names them deliberately — an override may be a break-glass credential — but nothing closes the loop, so the store grows. The `''` key from before the DHCP key fix is still there unless cleared by hand. | decide, then build | CLAUDE.md, *"`credential_profiles.json` is a secret store with no expiry"* |

## C. Tooling that reports wrongly

| # | Finding | Kind | Where recorded |
|---|---|---|---|
| C1 | **`nmas-deploy`'s behaviour is UNCONFIRMED, and the second report of it was a misreading.** *"Already at `da4d479` while `32329bf` exists on origin"* is correct behaviour: `32329bf` is an **ancestor** of `da4d479`, so the tip already contains it. The first report (*"already at `cfbe7fe`"* while origin was ahead, moved only by an explicit fetch) is not explained by that and may be real. **Status: needs one measurement** — `git fetch && git rev-parse HEAD origin/main` before and after a run. Whatever it does, it should end by printing both SHAs, because *"already current"* is a claim with operands and it was reported as a shrug. | verify, then build | this file — 2026-09-25 |
| C2 | **`routes/templatize.py`'s fleet report drops a device with an unreadable golden through a bare `continue`.** Fourth instance of *the artefact is not the population*; the other three are fixed. | build | CLAUDE.md, *"The inventory is the population for a RESTORE PREVIEW"* |
| C4 | **`health()` is per-process, and the recorder runs inside the app.** It counts in memory, so the figure `nmas-netbox-modified` prints is about the CLI and reads `0 writes failed` however badly the app is failing — *the reassuring zero, one level up*. The CLI now says so and names the app log as the channel that crosses processes; what remains undecided is whether the counters should be made durable at all, given the alternative is writing a failure report into the file that just failed to be written. | decide | [PHASE2_DHCP.md](PHASE2_DHCP.md) §21–§22 |
| C5 | **The deployment host does not run the deployment documented.** [DEPLOY_LINUX.md](DEPLOY_LINUX.md) describes a systemd unit `nmas` and `journalctl -u nmas`; the host runs `python3 app.py` as a bare process (PPID 1, no unit), so `journalctl -u nmas` answers `-- No entries --` — **the shape of "no failures"** — and that is the channel §22 and `nmas-netbox-modified` named for the recorder's failures. The CLI now reads `logs/device_manager.log` itself. What remains: install the unit, or document how the host actually starts the app — nothing records it, and the restart on every pull is done by something the repository does not describe. | decide | [PHASE2_DHCP.md](PHASE2_DHCP.md) §23 |

## D. Interface and input surfaces

| # | Finding | Kind | Where recorded |
|---|---|---|---|
| D1 | **`domain` is read by `_plan_args()` and no form sends it.** Recorded as *a gap under exemption* by `test_server_reads_nothing_the_form_cannot_send.py` rather than a clean pass — unlike `secret` and `source_kind`, there is no reason a person could not set it. | build | CLAUDE.md, *"the server may read nothing the form cannot send"* |
| D2 | **Whether a never-reached device should bind to a template is undecided.** Binding on the manifest entry is what makes the approval gate notice its population changed; it also takes a platform's deploy path offline until phase 2 completes. A test pins current behaviour so a change is a decision rather than a discovery. | decide | CLAUDE.md, *"Onboarding revokes its platform's template approval at CREATE"* |

## E. In the plan, but in no stage

These have acceptance criteria written and no stage owning them.

| # | Finding | Kind | Where |
|---|---|---|---|
| E1 | **Q2 — the Baselines badge and red-line labelling.** Colouring does not match what the entries mean. | build | NSOT_PLAN.md, *Queued from the Stage 2 session* |
| E2 | **Q3 — empty-command rejections at boot.** r3–r5 each logged two rejections of an empty command during the redeploy; the source of the blank line is unfound. Explicitly **not** to be silenced by filtering the log. | build | NSOT_PLAN.md, *Queued from the Stage 2 session* |
| E3 | **Tighten `transport input` on r1–r5.** They still carry `transport input all`. An ordinary authored-intent deploy, deliberately done one device at a time, scheduled after r6's branch site — which is now done. | build | NSOT_PLAN.md, *Deferred* |
| E4 | **Re-enable the drift checker.** Stage 3.3's one remaining item. The known-noisy check that would have fired first — regenerated self-signed certificates — is fixed, so the precondition is met. | verify, then enable | NSOT_PLAN.md, Stage 3.3 |

---

## Count

**15 open**: 12 recorded only in prose (A1–D2; C3 closed, C5 added), 4 in the plan without a stage
(E1–E4, one of which is Stage 3.3's tail).

By kind: **9 build**, **2 decide-then-build**, **3 decide**, **1 verify**.

None of them blocks Stage 7 — the per-stage scope and the ordering
constraints are in [NSOT_PLAN.md](NSOT_PLAN.md), *Scope of what remains*,
where **Stage 5's count is flagged as a reading of an acceptance paragraph
rather than an enumeration**: it is the one figure there with a different
provenance from the rest, and enumerating Stage 5 is the first item of Stage 5.

**A1 is the one whose absence makes other work untrustworthy** rather than merely incomplete: a mistake in NetBox has nothing
to restore from.

C1 was the second such item until it was measured, and the correction is worth
keeping: a finding recorded as a defect became the explanation for the next
confusing output, and that output was correct behaviour. *A pattern that has
been right four times is exactly the one to distrust on the fifth* — the
register makes a finding easier to find, and easier to reach for.

## Closed

| # | Finding | Closed | Reason |
|---|---|---|---|
| C3 | *"The recorder missed a confirmed write."* | 2026-09-25 | **Measured false.** The record holds the entry (`r1 comments … TEST → …`, `06:34:40Z`), the file's mtime is 0.18 s after NetBox's `last_updated`, the reader lists it, and the app log holds 0 recorder ERROR lines in 549,266. The positive control **passed**; it was read as failing. The misreading's mechanism is undetermined — the entry is the newest of 44, printed last, so any view of the output's head would omit it, but that is a candidate, not a measurement. [PHASE2_DHCP.md](PHASE2_DHCP.md) §23. |
