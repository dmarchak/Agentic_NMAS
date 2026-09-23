# Stage 4, step C — the onboarding wizard, proven on a probe

**Plan only. Nothing built yet.**

Governed by [NSOT_PLAN.md](NSOT_PLAN.md) and the decisions already taken in
[NSOT_PHASE4_ONBOARDING.md](NSOT_PHASE4_ONBOARDING.md) §8, which this does not
re-open.

**Step C is:** a new node with a **management interface only**, no data link,
**nothing existing touched**. r6 comes after this passes; the eBGP branch site
is a separate change after that.

---

## 0. What already exists, measured 2026-09-23

Worth stating so the plan is about the gap and not the whole.

| Piece | State |
|---|---|
| `bootstrap_config.render_bootstrap()` | **exists**, per-platform, ASCII-guarded |
| `repo.adopt_identity()` | **exists**; callers are `save_golden` (`allow_new`) and Add Device — the two the decision permits |
| `manifest.upsert_device()` | exists |
| NetBox write gate (`netbox_guard`, `netbox_authz`) | exists: `assert_writes_allowed`, `record_intent`, `record_created`, `issue_token` / `consume_token` / `verify_plan_unchanged` |
| `credentials.set_device_override()` | exists |
| `hostvars.write_committed()` | exists |
| `device.write_devices_csv()` | exists |
| **An onboarding blueprint** | **absent** — no `routes/onboard*.py` |
| **Any UI** | **absent** — `onboard` appears nowhere in `index.html` |
| Bootstrap credential rotation | **absent** as a wizard step (`credential_rotation` exists as a module) |
| RW `public` community removal | **absent** |

So the work is the **orchestration and its entry point**, not the primitives.

---

## 1. Build order

Each step is independently testable and leaves the tree green. **Negative
controls live in the suite, not in a runbook** — every acceptance item below
names the change that must make it fail.

### 4C.1 — `modules/nsot/onboard.py`: the plan object

A frozen dataclass `OnboardPlan` plus `build_plan()`, the **only**
constructor, mirroring `render_artifact.build_artifact()`. It computes:
target list and source kind (local vs NetBox), platform, hostname, management
address, credential resolution and its `_cred_source`, the NetBox object plan,
the `host_vars` document, the bootstrap config text, and `blocking_reasons`.

`onboardable` is a **computed property**, never an argument — the
`render_artifact` lesson, which is why `deployable` cannot be set by a caller
that forgot to check.

*Acceptance*
- A plan with a name colliding in the manifest **or** in NetBox is refused,
  naming which. Not a warning: §4 step 2 of the onboarding doc.
- A plan for an unapproved template is refused with the reason.
- `blocking_reasons` carries every refusal at once, not the first.
- **Negative control:** make `onboardable` settable → a test asserting
  `build_plan` is the only constructor fails.

### 4C.2 — The bootstrap credential: random, one-time, rotated at the end

`onboard.mint_bootstrap_credential()` generates a random password per run,
used **only** to reach the device for its first capture, and the final wizard
step calls the existing rotation to replace it with a device-generated
type-9 secret.

*Acceptance*
- Two runs produce different credentials (seeded-RNG test, not a smoke test).
- The bootstrap value is **never** written to `devices.csv` or the credential
  store as a durable value — it lives in the staging path the rotation
  already uses, and `assert_no_secret_values()` covers it.
- The run records that rotation **happened**, and a run where rotation failed
  reports `rotated: false` with the reason rather than reporting success.
- **Negative control:** stub the rotation to fail → the wizard reports the
  device onboarded **and not rotated**, and a test asserts it does not claim
  success. This is the `mark_done()` rule: an item closed on a failed push is
  the queue claiming work that did not happen.

### 4C.3 — Ordering and partial failure

Implemented exactly as §3 of the onboarding doc, because that order was chosen
by what is recoverable: credential binding → NetBox (gated) → **one commit**
(identity minted + `host_vars` + site `group_vars`) → render → download/deploy.

*Acceptance*
- A failure at the NetBox step leaves **nothing** committed, and says so.
- A failure after NetBox offers the existing provenance-based Remove directly,
  rather than leaving the operator to find it.
- **One commit per run**, trailers naming site and device — asserted by
  counting commits, not by reading a message.
- **Negative control:** split the commit in two → the count assertion fails.

### 4C.4 — `routes/onboard.py` + `templates/partials/onboard_wizard.html`

The seven steps from §4 of the onboarding doc. **Ships with its entry point**
— a button on the Devices toolbar — and is covered by the per-route
reachability check, not only the blueprint one.

*Acceptance*
- Every route the wizard defines appears in the rendered page.
- The review step shows the NetBox plan, the `host_vars` YAML and the
  **masked** render, and states that the deploy re-renders with real secrets.
- The credential step displays `_cred_source`.
- **Negative control:** remove the toolbar button → the reachability test
  fails, naming the route.

### 4C.5 — RW community removal, during onboarding

vrnetlab nodes arrive with a read-**write** `public` community. Removed as
part of onboarding, not after — the history scan acknowledged nine read-only
communities; anything RW arriving with a new node is a different matter.

*Acceptance*
- A capture containing `snmp-server community public RW` produces a removal
  line in the program, and the confirm names it.
- The nine existing RO communities are **not** touched — a test with the
  fleet fixtures asserts no RO line is proposed for removal.
- **Negative control:** widen the match to any `snmp-server community` → the
  RO-untouched test fails.

### 4C.6 — Drift enrolment (your item 4, and it gets its own step)

After 3.3b the drift population **is the inventory**, so a device becomes
drift-covered the moment it is in the inventory — not when a golden appears.
That is the property to prove, because it is exactly what was silently wrong
before Stage 3.3: the device would have had a repo golden, no legacy file, and
been invisible to the checker with nothing saying so.

*Acceptance*
- Immediately after onboarding, `run_drift_check()` reports
  `inventory == N+1` and the new device in **exactly one** bucket.
- With its golden captured, coverage reads **`checked N+1 of N+1`**.
- Between inventory insert and first capture it reports **`no golden config
  saved`** — named, not absent. "Not yet captured" and "invisible" are
  different states and only one is acceptable.
- **Negative control:** point the drift population back at
  `_list_golden_configs()` → the new device vanishes from the counts and the
  coverage assertion fails. This is the 3.3b control re-run against a device
  that did not exist when 3.3b was written.

---

## 2. What the wizard emits, and the generator rules that apply

The wizard **generates the startup config a new node boots from**, so every
per-platform rule in `bootstrap_config.py` is on this path.

| Rule | Status |
|---|---|
| `transport input ssh` on **both** platforms | **done**, `81375e7` |
| ASCII only over the **whole** rendered text, comments included | `assert_sendable()`, existing |
| No prose comments at all on console-replayed platforms | existing, `CONSOLE_REPLAYED` |
| `end` only as the final line | `push_safe_lines()` is a truncation guard; the bootstrap render ends with `end` and nothing follows |
| `password 0` vs `secret 0` per `VRNETLAB_INJECTS_USER` | existing — the stage B/C lesson |
| `ip domain name` vs `ip domain-name` | existing — the stage C finding |

*Acceptance*: the wizard's emitted text goes through `assert_sendable()` over
the whole output before it can be downloaded or deployed, and a test feeds it
a non-ASCII site description to prove the guard is on **this** path and not
merely on the deploy path.

**Negative control:** bypass `assert_sendable()` in the wizard's emit path →
the em-dash test fails.

### Stage D and step C — they do not interact

**Measured:** r6 and the probe node for step C are **C8000v**, and
`cisco_iosxe` is in **neither** `GENERATES_SSH_KEY` nor `CONSOLE_REPLAYED`.
The C8000v bootstrap render contains **no `crypto key generate rsa` line at
all** — 15 lines, verified.

So **step C does not depend on stage D.** Stage D measures a line the C8000v
path never emits and a replay mechanism the C8000v never uses. It remains
required before any **vIOS** is onboarded, which is what the four switches
run, and the wizard must refuse a `cisco_ios` target until it has passed —
which is itself an acceptance item:

- Selecting a `cisco_ios` platform in the wizard **refuses**, naming stage D,
  until a recorded pass exists.
- **Negative control:** remove the refusal → a test asserting a vIOS target is
  blocked fails.

---

## 3. The probe: what it runs against, and teardown

Same isolation rules as the bootstrap probe — **own lab name, own network, own
subnet, nothing shared with `rcn-lab1`.**

- New file `docs/bootstrap-probe/nmas-onboard-c.clab.yml`, one node,
  `bp-onboard-c`, kind `cisco_c8000v`, its own `mgmt` network on a subnet not
  used by any other probe lab, and `startup-config` **absent** — the point is
  that the wizard generates it.
- The node is created empty, the wizard onboards it, and every artefact the
  wizard produces is inspected: NetBox objects, the commit, the golden, the
  extraction, the committed intent, the drift coverage.
- **A temporary device list**, not `default` — so the probe's NetBox objects,
  manifest entries and commits land in a repo that is thrown away. The
  `conftest.py` guard already refuses tests writing into live lists; this is
  the operational equivalent.
- **Teardown:** `containerlab destroy --cleanup`, the probe's NetBox objects
  removed through the existing provenance-based Remove (which is itself worth
  exercising), the temporary list deleted, and
  `scripts/nmas-check-secret-storage` run to confirm the bootstrap credential
  left nothing behind.

*Acceptance*: after teardown, `data/lists/` holds only the real lists, no
`nmas-managed` NetBox object remains from the probe, and the secret-storage
check exits 0.

---

## 4. Test files

| File | Covers |
|---|---|
| `test_onboard_plan.py` | `build_plan` the only constructor; collisions refused in both stores; every blocking reason at once |
| `test_onboard_ordering.py` | order, partial failure, one-commit-per-run, Remove offered on failure |
| `test_onboard_bootstrap_credential.py` | randomness, never durable, rotation reported honestly |
| `test_onboard_emits.py` | ASCII over the whole output on the wizard's own path; platform rules; vIOS refused pending stage D |
| `test_onboard_drift_enrolment.py` | `checked N+1 of N+1`; "no golden config saved" named before first capture |
| `test_onboard_snmp.py` | RW removed, the nine RO untouched |
| Reachability | every wizard route present in the rendered page |

---

## 5. Decisions taken

**1. The probe runs on a `local` list.** Immediate drift enrolment is the
property worth proving; a NetBox-sourced list makes 4C.6 depend on the
refresh loop rather than on the wizard. The NetBox-sourced flow is a separate
exercise afterwards with its own acceptance.

**2. The probe writes to the real NetBox — approved, with a condition.**

The teardown *is* the test. The provenance-based Remove has existed since
Phase 0 and **has never been exercised against objects it created itself**.
Better to find out it leaves something behind with a probe device than with
r6. A dry-run-only proof would test the preview and not the write, and the
write through the gate is the interesting part.

**The condition: NetBox object counts are recorded before the run and
asserted equal after teardown** — devices, sites, interfaces, prefixes, IP
addresses, VRFs, VLANs and cables. *"Remove cleaned up"* measured, not
eyeballed. Any difference is a finding, and a number is better than an
absence.

That needs a tool, so it becomes its own build step:

### 4C.0 — `scripts/nmas-netbox-census`

Counts every object type the NetBox tab shows, prints them as a table, and
writes a JSON snapshot. A second invocation with `--compare <snapshot>`
prints the delta per type and exits 1 on any difference.

**Two things the obvious version would not have had:**

**Identity, not counts.** Counts can match while the contents differ: Remove
deletes the probe's prefix, something else creates one during the run, the
total returns to baseline, and the probe's object is gone-but-replaced. *"The
same objects"* is the claim; *"the same number"* is a proxy for it. The
snapshot records `id:label` per object per type, and `--compare` says so in
those words when a count matches and the contents do not.

**Tagged counted separately from the total.** The real NetBox already holds
`nmas-managed` objects from the Lab 1 import, and **the population Remove may
touch is the tagged one** — so the tagged before/after is the number that
actually tests the provenance gate. A total that matched while the tagged set
drifted would be a pass hiding a failure, and is now its own finding.

*Acceptance*
- Run before the probe and after teardown; `--compare` exits 0.
- Per **object type**, not a total: a device removed and a prefix left behind
  must not cancel out.
- It names what it does **not** count, so the claim has an edge — the same
  rule as `nmas-check-secret-storage`. A test asserts the counted list has
  not fallen behind the endpoints `netbox_client` actually touches.
- A census that could not be taken **raises** rather than writing a file that
  would later compare clean.
- **Negative control:** create one tagged object and leave it → `--compare`
  exits 1 and names the type. Asserted in the suite *and* run as part of the
  probe.

---

## 6. Previously open, now closed

Three of the four open questions in the onboarding doc §7 are answered by §8.
**Question 3 is not**, and step C makes it concrete:

> **Does the wizard write `devices.csv`?** For a local list it must, or the
> device is invisible to every other part of the app. For a NetBox-sourced
> list identity is read-only and the device arrives on the next refresh.

Step C's probe runs on a **temporary list**. If that list is `local`, the
wizard writes the CSV and drift enrolment is immediate. If it is `netbox`, the
device appears only after a refresh, and *"checked N+1 of N+1"* is not
assertable until that refresh completes — which changes acceptance 4C.6 from
"immediately" to "after the next refresh, and the refresh is part of the run".

Both are decided in §5 above: **`local`**, and **write to the real NetBox**
with the census condition.

---

## 7. Progress

| Step | State |
|---|---|
| **4C.0** the NetBox census | **done** — `scripts/nmas-netbox-census`, `tests/test_netbox_census.py`, 15 tests, three negative controls each shown failing |
| **4C.1** the plan object | **done** — `modules/nsot/onboard.py`, `tests/test_onboard_plan.py`, 27 tests, four negative controls each shown failing |
| 4C.2 bootstrap credential | not started |
| 4C.3 ordering | not started |
| 4C.4 routes + UI | not started |
| 4C.5 RW community | not started |
| 4C.6 drift enrolment | not started |
