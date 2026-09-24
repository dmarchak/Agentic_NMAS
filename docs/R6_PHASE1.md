# r6, phase 1 — a permanent tenth device on br-mgmt

**One variable: the device is permanent.** Everything else is the path the
Stage 4C probe walked on 2026-09-24 — same kind (`cisco_c8000v`), same
bridge, same wizard, same two-phase onboarding, same launch patch.

Phases 2 (address from Kea instead of the config) and 3 (behind a switch,
with the relay) each change one further variable and are not in scope here.

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

**What the Baselines panel will show: exactly what it shows today.**
`repo.list_baselines()` returns tag, creation date and subject — **it
computes no coverage**. Every existing baseline will keep rendering as it
does now. The only hint is inside the subject text of baselines created by
an unchanged Save All:

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
  it.** `clab_configs_dir` and the redeploy tooling point at rcn-lab1; r6's
  startup config lives beside its own topology and needs its own entry
  before any claim that r6 survives a host reboot. **Phase 1 does not make
  that claim.**
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

## Step 1 — close the restore-preview gap (0b)

Not optional, and it comes first: after step 6 every existing baseline is
partial, and the tool should say so before that is true rather than after.

**Acceptance:** a restore preview against a ref that predates a device in
the inventory names that device, and the confirm reads *"N of M"*.

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

## Step 7 — the first fleet baseline of ten

**Save All.** Expect a single commit, ten devices, and a `baseline/<ts>`
tag whose subject names ten.

**A baseline naming nine is the finding**, not a rounding error: it means
r6 was not in the inventory when the batch was judged, and `coverage still
governs`.

---

## What phase 1 does NOT establish

Stated so it is not assumed later:

* **that r6 survives a host reboot** — the persistence pipeline does not
  know about its lab yet (0c);
* **anything about DHCP** — the address is static, from the config. That is
  phase 2, and phase 2 exists precisely to separate *"does the device fetch
  and apply"* from *"does the relay work"*;
* **anything about the fabric** — r6 is L2-adjacent to the NMAS with no
  routing. Phase 3 adds the switch, the relay and `Loopback0`.
