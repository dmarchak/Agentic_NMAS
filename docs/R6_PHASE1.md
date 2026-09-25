# r6, phase 1 — a permanent tenth device on br-mgmt

**One variable: the device is permanent.** Everything else is the path the
Stage 4C probe walked on 2026-09-24 — same kind (`cisco_c8000v`), same
bridge, same wizard, same two-phase onboarding, same launch patch.

Phases 2 (address from Kea instead of the config) and 3 (behind a switch,
with the relay) each change one further variable and are not in scope here.

---

## Where r6 stands — PHASE 1 CLOSED, 2026-09-24

**Read this first.** It is the state, not a summary of the plan.

### r6 is a full member of the fleet

* **Onboarded by the wizard and promoted** — in the manifest, in NetBox
  (`netbox_id 10`), in `devices.csv`, verified at 03:42:21.
* **Rotated** — the CSV carries the rotated credential, the device holds a
  device-generated `secret 9`, `admin`/`admin` refused,
  `nmas-check-credential r6 --expect` → **ACCEPTED, exit 0**.
* **First golden committed** — 6,907 bytes, tagged
  `golden/bp-onboard-c/20260924T034213Z`, **no `snmp-server` RW line**,
  because the removal ran before the capture.
* **In the break-glass record** — re-exported for **ten**, verified
  `complete: True`.
* **`cisco_iosxe/base.j2` approved against six devices**, which is what
  binding r6 revoked at Create.
* **A fleet baseline of ten**; every earlier baseline now renders
  `9 of 10 — partial · predates r6`.

### It is reboot-safe, and that is measured rather than assumed

`labs/r6/configs/r6.cfg` is the sanitised 74 lines: **`secret 9` present,
`password 0` absent**. `nmas-check-startup-applies r6` reads:

```
r6  SAFE  cisco_iosxe  username admin privilege 15 secret 9 <redacted>
    dmarchak@10.0.0.210:labs/r6/patches/c8000v-launch-adopted.py@e483dd2475b5
```

**Naming r6's own launch patch rather than the default lab's** — the
device → lab map resolving correctly through the whole chain, which is the
thing that check exists to prove.

The sync run's own accounting agreed: the destination count and the `cmp -s`
read-back both fired and reported **10 of 10**.

### The lab is versioned

`~/labs/r6` is a git repo tracking exactly `.gitignore` and
`configs/r6.cfg` — the same shape as `~/labs/lab`, which was **read rather
than guessed** (`git -C ~/labs/lab ls-files`) and tracks only `configs`.

`~/labs/lab`'s history was checked for the secrets exposure that a bare
`git add -A` caused in r6's first attempt: `git log --all --name-only` finds
no `.key`, no `.tls/`, no `.state`. **Nothing to rewrite**, and the check was
worth making — a null result from a question that could have been expensive
is a result.

### Nothing from phase 1 is open

The sync half is done: `~/bin/clab-sync` and
`~/lab-configs/oxidized-to-config.sh` take the map from
`nmas-clab-targets`, write per destination, and report per lab. The whole
file is `docs/patches/oxidized-to-config.sh.new`.

### Next

1. **The Oxidized freshness comparison**, four parts in order: the Oxidized
   **read client** and the sanitiser's pre-write **gate** first, since those
   stop an unapproved state becoming durable; the **Monitoring signal**
   after. Authorisation path included — a gate with no way through gets
   disabled, which is how the drift checker was lost for 24 days. The
   comparator it needs is correct as of `747e506`.
2. **Then phase 2 (address from Kea) or the branch site** — operator's
   choice, not a sequencing constraint.

Stages 5, 6, 7 and 8 are unchanged. **There is no separate settings
rebuild** — Stage 3.2a is shipped and what remains is 7.7 inside Stage 7;
see NSOT_PLAN.md, *Scope of what remains*.

---

## 0. What is different from the probe, up front

Most of this is proven. These four things are not, and three of them are
decided below rather than discovered on the night.

### 0a. r6 is permanent — no baseline, no teardown

The probe's central claim was that **Remove cleans up what it created**, so
it needed a census baseline before and a measured teardown after. r6 is not
removed, so:

* **no `nmas-netbox-census --out` baseline** is required, and step 0a of
  [STAGE4C_PROBE.md](STAGE4C_PROBE.md) does not apply;
* **no `--compare`**, no Remove, no list deletion;
* its NetBox objects **stay**, and the three-object region/site/VRF
  scaffolding is wanted rather than residue.

Take a census anyway (`--out ~/r6-before.json`), for a different reason: it
makes "what did onboarding create" a **diff rather than a recollection**,
which is the same argument as the NetBox-backup plan item. It is evidence,
not an acceptance gate.

**The break-glass record does NOT cover r6, and that is step 6b.**
`nmas-breakglass export --list Default` snapshots the list **at the time it
runs**; the existing record was exported for nine. Until it is re-exported,
r6's credential exists in exactly one place — `devices.csv`, encrypted with
`data/key.key`, on the NMAS. **A tenth device absent from the record is a
device with no recovery path at all**, which is precisely the state stage B
measured and the record was created to prevent.

It must be re-exported **after** rotation, not before: the record has to
hold the *rotated* credential, for the same reason promotion goes last.

### 0b. It joins the Default list, so baselines change meaning

This is the item with a gap in it, and the gap is worth closing before the
night rather than during it.

**What is correct already.** After r6's first Save All the inventory is ten
and the new `baseline/<ts>` covers all ten. `_baseline_earned()`
(`routes/deploy.py`) reads the **current** inventory, so a restore to any
pre-r6 baseline is **denied the tag** and says why, naming the device:

```
1 device(s) were not measured against baseline/2026…: ['r6']
```

**What the Baselines panel will show** — corrected after reading
`routes/golden.py` rather than only `repo.list_baselines()`, which returns
tag, date and subject alone. The panel adds
`entry["device_count"] = len(devices_at(repo, tag))`, so an older baseline
renders **9** and a newer one **10**. The difference is therefore *visible
as a number* and is **never named as partial** — and a number is not a
statement. The subject text of baselines from an unchanged Save All says:

```
network baseline — no changes; all 9 capture(s) verified equal to HEAD
```

and that `9` is a historical fact about the night it was written, not a
statement about today's fleet.

**The gap.** `restore.plan()` iterates `for hostname in sorted(at_ref)` —
the devices **at the ref**. A device in today's inventory with no golden at
that ref is therefore **absent from the preview entirely**: not an error,
not a skip, not named. Restoring to a pre-r6 baseline will present nine
devices and say nothing about the tenth.

That is textually the drift checker's *"all 9 device(s) clean"* over a
ten-device inventory, which this project has already fixed once. **Close it
before r6 joins the list**, because the moment it does, every existing
baseline silently becomes a partial restore point:

* `restore.plan()` reports inventory devices with no golden at the ref, with
  a reason (*"this ref predates r6"*), the way stale devices are reported;
* the confirm dialog states *"restores 9 of 10 devices"* rather than a
  number that reads as complete;
* the Baselines panel labels a baseline **partial** when
  `devices_at(ref)` does not cover the current inventory.

### 0c. Topology — no redeploy, and no outage

**Phase 1 does not touch `rcn-lab1.clab.yml` at all**, so the question of
whether containerlab can add a node to a running lab does not arise. It is
phase 3's question, when r6 needs a real link to an s-node *inside* that
lab.

`docs/bootstrap-probe/nmas-onboard-c.clab.yml` already proved the pattern:
its **own** lab name, its **own** containerlab management network, and a
`kind: bridge` node declaring `br-mgmt` — a Linux bridge on the clab host
that **neither lab creates and neither owns**. rcn-lab1 declares it exactly
the same way. r6 gets `r6.clab.yml` built from that file, with a permanent
lifecycle instead of a teardown.

Two consequences worth stating now:

* **The lab is separate, so the persistence pipeline does not know about
  it — and that is not a footnote.** rcn-lab1's nine survive a rebuild
  because clab-sync writes harvested configs back to their startup files.
  r6 has no such path, so **a clab host reboot brings r6 back on its
  BOOTSTRAP config**: `password 0`, no rotated credential, and NMAS locked
  out of a device it manages and believes it has rotated.

  **That is the stage B failure arriving by a different route** — a node
  that boots, reports healthy, answers SSH and holds a credential nobody
  has — and it is **live from step 6 onward**, not at some later phase.

  Tonight proceeds anyway, because the exposure is bounded by the
  break-glass record (6b) and a reboot is a deliberate act. But it gets a
  **deadline, not an open end**, and one of these two happens:

  1. **r6's lab joins the persistence sync before phase 2 begins** — the
     preferred outcome, since phase 2 changes how the address arrives and
     should not also be carrying an unresolved reboot hazard; or
  2. **"What phase 1 does not establish" gains a line stating the device is
     NOT reboot-safe**, naming clab-sync coverage as the thing that would
     make it so — so the gap is recorded where somebody reaching for r6
     will read it, rather than in a runbook nobody opens twice.

  The second is the fallback and the first is the intent. Neither is "we
  will get to it". **Scoped in [R6_PERSISTENCE.md](R6_PERSISTENCE.md)**,
  which found that the launch-patch setting is the more dangerous half:
  fixing only the configs directory would make `verify_startup_applies()`
  check rcn-lab1's patch for a device r6's own patch boots, and pass.
* A future `containerlab destroy --cleanup` on rcn-lab1 must not disturb
  r6. It has its own lab name and its own veth, so it will not — but this
  is the same *"what does `--cleanup` do to a bridge node it did not
  create"* question the probe measured on a scratch bridge (step 3c), and
  the answer it produced applies unchanged.

### 0d. Address: `10.255.0.32`

`.31` stays the probe convention and is not reused. `10.255.1.16` belongs
to phase 3, with `Loopback0` and OSPF; phase 1 has **no routing** — the
NMAS shares the `/24` and always initiates, which is the whole reason this
position was chosen. The generator emits one interface stanza and no route,
via `manager_interface_lines()`.

**Verify it free three ways before using it**, as `.31` was: NetBox holds
nothing on it, no ping reply, and the neighbour table shows it `INCOMPLETE`.

---

### ⚠ Before diagnosing ANY "the page ignores the data" symptom

The app is behind a Cloudflare tunnel, **the edge caches HTML and does not
cache JSON**, and a browser hard-reload does not bypass it. So a page can be
hours old while every endpoint it fetches is current — which looks exactly
like a value computed, carried to the browser and drawn nowhere.

Measured 2026-09-24: the Baselines panel drew a bare *"9 device(s)"* while
`/golden/baselines` returned `partial: true`. `?x=1` rendered it correctly.
The code had been right the whole time, and the wrong diagnosis was made
because that shape had been a genuine defect **four times the same night** —
*the more instances of a shape you have found, the more likely you are to
misattribute the next thing that resembles it.*

**Ask the origin first. One command, and it partitions the space:**

```bash
curl -s http://10.0.0.211:5000/ | grep -c '<helperNameOrMarkup>'
```

* **≥1** — the origin is current; the staleness is the edge. Add `?x=1` or
  purge. **Stop reading the code.**
* **0** — the origin does not have it. *Now* it is a deploy or a code
  question.

---

## Step 1 — close the restore-preview gap (0b)

Not optional, and it comes first: after step 6 every existing baseline is
partial, and the tool should say so before that is true rather than after.

**Acceptance:** a restore preview against a ref that predates a device in
the inventory names that device, and the confirm reads *"N of M"*.

**Done**, with the survey that was asked for alongside it — *how many other
readers iterate an artefact where the inventory is the right population.*
**Three, two now fixed:** `drift_check` (corrected in Phase 3.3),
`restore.plan_restore()`, and the **Baselines panel**, whose `device_count`
came from `devices_at()` with no reference to the inventory.

Correct as they stand, listed so the next survey does not re-check them:
`_baseline_earned()` reads the current inventory; `event_monitor` iterates
the **inventory** and looks the artefact up, which is the right way round;
`check_runner` and `pipeline_builder` build CI checks from goldens, where
the artefact genuinely is the population — though **neither states its
coverage**, a smaller version of the same thing; and the `next(...)` lookups
in `routes/deploy.py` and `routes/templates.py` are single-device, not
populations.

**A fourth exists and is not fixed:** `routes/templatize.py`'s fleet
validation report iterates goldens and drops a device with an unreadable one
through a bare `continue`. Recorded rather than fixed blind, for when that
panel is next touched. `ai_assistant`'s copies are Stage 8 and already
recorded as deferred.

---

## Step 2 — census, as evidence

```bash
python scripts/nmas-netbox-census --out ~/r6-before.json
```

**Not an acceptance gate** (nothing is torn down), so this step does not
block. It exists so "what did onboarding create for r6" is a diff.

---

## Step 3 — verify the address and the bridge

```bash
# free, three ways
curl -s "$NB/api/ipam/ip-addresses/?address=10.255.0.32" | python -c "import json,sys; print(json.load(sys.stdin)['count'])"
ping -c2 -W1 10.255.0.32 ; ip neigh show 10.255.0.32

# br-mgmt exists and what is on it
ip -br link show master br-mgmt
```

Expect `0`, no reply, `INCOMPLETE`, and a bridge holding the host uplink,
`s3-mgmt`, and nothing named `r6-mgmt`.

**If `probe-mgmt` is still on the bridge**, the probe's node was not
destroyed. Stop and clear that first — an orphaned veth is how two labs
come to disagree about who owns a wire.

---

## Step 4 — stage the launch patch, r6's own copy

```bash
mkdir -p ~/labs/r6/patches ~/labs/r6/configs
cp ~/labs/lab/patches/c8000v-launch.py ~/labs/r6/patches/c8000v-launch-adopted.py
```

**Both halves are load-bearing and one of them is silent** — `smp="2"`
fails loudly and costs forty minutes; the **user-skip** fails by
succeeding, booting on `admin`/`admin` while reporting healthy. Confirm the
skip is present in the copy before continuing; `test_probe_topologies.py`
asserts the binding exists, not that the file is the right one.

---

## Step 5 — the wizard, through the GUI

Every action through the interface, the shell only to read state
afterwards — the probe's method, and the reason it found seven defects the
suite passed.

* **List: `Default`**, chosen explicitly in the form. It is an ordinary
  field and it is carried, never derived.
* Hostname `r6`, platform `cisco-ios-xe`.
* **Manager interface `GigabitEthernet2`**, address `10.255.0.32`, mask
  `255.255.255.0`. Gi1 is vrnetlab's; the generator refuses to guess.
* Read the review screen before pressing Create. Template approval appears
  as an **advisory**, not a blocker.

Then **download the bootstrap artefact** from the pending row
(`GET /onboard/bootstrap/r6`) — it is a reveal, gated on a person and
recorded. Write it to `~/labs/r6/configs/r6.cfg`.

---

## Step 6 — deploy r6's own lab, and onboard it

`~/labs/r6/r6.clab.yml`, built from `nmas-onboard-c.clab.yml`: own lab name
`r6`, own `mgmt.network`/subnet (**not** `clab-onboard-probe` and not
rcn-lab1's), `startup-config: configs/r6.cfg`, the bind to
`patches/c8000v-launch-adopted.py`, and one link
`["r6:Gi2", "br-mgmt:r6-mgmt"]`.

Boot is ~6m30s. Then **Verify** from the pending banner — phase 2 of
onboarding, seven steps: verify → capture → rotate → remove RW → golden →
NetBox → promote.

**Expected, and each is a claim to check rather than skim:**

* `secret 9` on the device, `password 0` absent, `admin`/`admin` refused;
* the RW community removed **verbatim**, the RO community untouched;
* the first golden contains **no `snmp-server` RW line** — removed before
  the capture;
* `devices.csv` carries the **rotated** credential, not the bootstrap one;
* `nmas-check-credential r6 --expect` → **ACCEPTED, exit 0**;
* Gi1's `10.0.0.15/24` is **not** imported into NetBox — `netbox_excluded_vrfs`
  covers `clab-mgmt`. This is the first run where that exclusion matters on
  a device that is not being thrown away.

---

## Step 6a — ⚠ the platform's approval is already revoked, and has been since step 5

**Confirmed from the code before the night, not assumed.** Checked because
the alternative — approval surviving a new binding — would be the gate not
noticing its own population changed, in the place that would be most
dangerous.

It works as designed, and three things about *when* are not obvious:

**1. It happens at Create, not at Verify.** `devices_for_template()`
computes the bound set from the **manifest, every time** — never a stored
list — and applies **no `pending` filter**. Onboarding's `commit_step`
writes r6 into the manifest in phase 1. So from the moment Create succeeds,
`cisco_iosxe/base.j2` is bound to **six** devices and its stored fingerprint
covers five.

**2. A Deploy plan for r1 therefore refuses on approval from step 5**, not
from step 6 — through the whole ~6m30s boot and until Verify completes.
**This is what to check, and the expected answer is that it refuses.** If a
deploy to r1 still passes its approval gate while r6 sits in the manifest,
**that is the finding**: the gate would be reading a population it no longer
has.

**3. It cannot be cleared by re-approving.** `POST /templates/approve`
collects bound devices with no captured config and returns **400 naming
them** — *"A template cannot be approved against a device it has never been
validated on."* That refusal is the load-bearing one: had it instead skipped
them, `approve()` would have validated five devices and stored a fingerprint
covering six, which is the same defect one layer down.

**So phase 1 takes the cisco_iosxe cohort's deploy path offline**, and there
are exactly two exits: **complete step 6** (r6 gets a golden, approve
against six), or **abandon r6** (`manifest.release()` removes the entry and
the old fingerprint matches again). If step 6 fails and r6 is left pending,
the block persists — which is correct, and is worth knowing before it is
discovered at 01:00.

**Check on the Template library after step 6:** `cisco_iosxe/base.j2` reads
**not approved**, `approval_status()` names r6 as the change, and approving
it validates against **six** devices. A count of five is the finding.

*(Whether a device that has never answered SSH ought to bind at all is a
real question — it has no committed intent and cannot be deployed to, so
binding it blocks its cohort and achieves nothing else. Not changed here:
binding on the manifest entry is exactly what makes the gate notice its
population changed, and that property is worth more than the window is
worth avoiding. Pinned by a test either way, so a later decision is a
decision rather than a discovery.)*

---

## Step 6b — re-export the break-glass record, for ten

```bash
python3 scripts/nmas-breakglass export --list Default --out /media/usb/rcn.bg
python3 scripts/nmas-breakglass verify /media/usb/rcn.bg
```

**After rotation, before the night is called done.** The record must hold
r6's *rotated* credential; exporting before step 6 would record the
bootstrap one, which is worse than not recording it — a recovery path that
produces a credential the device no longer accepts.

`verify` names the devices it covers. **Expect ten.** Nine is the finding.

---

## Step 7 — the first fleet baseline of ten

**Save All.** Expect a single commit, ten devices, and a `baseline/<ts>`
tag whose subject names ten.

**A baseline naming nine is the finding**, not a rounding error: it means
r6 was not in the inventory when the batch was judged, and `coverage still
governs`.

### ⚠ This baseline is not a restore point FOR r6

At phase 1 r6 is a router with a management address and nothing else. So
the first baseline covering ten is **correct as a record and wrong as a
target**: re-applying it would restore r6 to a bootstrap-shaped config —
which is exactly what r6 looked like at that moment, and is not a state
anybody will want to return to once phase 3 has given it `Loopback0`, OSPF
and a position in the fabric.

Nothing in the tool can know that. It is the same class as the credential
staleness warnings on the Baselines panel — a ref that is internally
consistent and is nonetheless the wrong thing to reach for — and it is
recorded here for the same reason those are shown beside the button rather
than after it.

**The first baseline that is a meaningful restore point for r6 is the one
taken after phase 3.** Until then, treat r6's entry in any baseline as *"it
existed and had an address"*.

---

## What phase 1 does NOT establish

Stated so it is not assumed later:

* **that r6 survives a host reboot.** It does not. A clab host reboot
  brings it back on its **bootstrap config**, with `password 0` and no
  rotated credential — recoverable only through the console and the
  break-glass record. What would make it reboot-safe is **clab-sync
  coverage of r6's lab**, and 0c sets the deadline for that;
* **anything about DHCP** — the address is static, from the config. That is
  phase 2, and phase 2 exists precisely to separate *"does the device fetch
  and apply"* from *"does the relay work"*;
* **anything about the fabric** — r6 is L2-adjacent to the NMAS with no
  routing. Phase 3 adds the switch, the relay and `Loopback0`.
