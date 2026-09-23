# Stage 4C probe — onboard a node that does not exist, then remove every trace

**Not yet run.** Same form as stages B, C and D2: numbered steps, commands
you run, output you paste, **one step at a time**.

This is the first end-to-end exercise of the onboarding wizard, and the
**teardown is the part that has never run**: the provenance-based Remove has
existed since Phase 0 and has never been asked to delete objects it created
itself. Better to find out it leaves something behind with a probe device
than with r6.

---

## Before you start

**Have open:**

| | why |
|---|---|
| A terminal on the **NMAS host** | every command below runs there |
| A terminal on the **containerlab host** | steps 3 and 11 only |
| The **console** for the probe node (`docker logs -f …`) | step 3 — the boot is the measurement |
| The **Devices tab**, Onboard wizard | steps 5–7 |
| The **Approvals tab**, drift panel | step 9 — coverage |
| The **Golden tab**, Remote card | step 8 — the commit |
| `before.json`, the census baseline | step 2, compared at step 12 |

**Roughly 45 minutes**, most of it waiting for a C8000v to boot.

### What touches what

| | steps |
|---|---|
| **Local only** — NMAS host, nothing shared | 0, 1, 2 (reads NetBox), 4, 5, 6, 7, 9, 10, 13, 14 |
| **Shared: the containerlab host** | **3**, **11** |
| **Shared: the real NetBox — writes** | **8**, **12** |

Steps 8 and 12 are the only ones that change NetBox. Step 2 reads it.

### If a step fails

**Stop and measure. Do not retry, and do not clean up.** A failed step is the
measurement; a retried step has destroyed it, and a cleaned-up failure cannot
be diagnosed. Paste the output and wait.

**One exception, stated because it is the case where waiting is wrong:** if a
node is left booted with a staged bootstrap credential and you need back in,
the credential is recoverable — it is encrypted in
`data/lists/<list>/config_repo/.nsot/staging/credential/<hostname>.enc` and
readable with:

```bash
python -c "
from modules.nsot.onboard import staged_bootstrap_credential
print(staged_bootstrap_credential('data/lists/nmas-probe/config_repo','bp-onboard-c'))"
```

That is the whole point of staging it (4C.2): between the node booting with
it and rotation replacing it, it is the only way in. Recovering it is not
cleaning up — it changes nothing — so it does not break the rule.

---

## Step 0 — enable NetBox writes, deliberately

**Local.** An explicit operator action, and the wizard will not do it for
you: a switch flipped as a side effect of confirming something else is not a
decision anybody made.

Settings → Integrations → **Allow writes to NetBox** → on. Then:

```bash
curl -s localhost:5000/settings/integrations | python -m json.tool | grep -i allow_writes
```

**Proves:** the gate is open because you opened it.
**If it fails:** the wizard will name it as a blocking reason at step 6 — that
is the designed behaviour, not a problem to work around.

> **Turn it off again at step 13.** It defaults off and should end off.

---

## Step 1 — a temporary list, not `default`

**Local.** Everything the probe creates lands in a repo that gets thrown away.

```bash
curl -s -X POST localhost:5000/device_lists \
  -H 'Content-Type: application/json' \
  -d '{"name": "nmas-probe"}'
ls -la data/lists/ | grep nmas-probe
```

**Proves:** a `local` list exists, per the §5 decision — immediate drift
enrolment is the property worth proving, and a NetBox-sourced list would make
step 9 depend on the refresh loop instead of the wizard.
**If it fails:** stop. Everything after this writes into that list.

---

## Step 2 — the census baseline

**Reads the real NetBox. Writes nothing.**

```bash
python scripts/nmas-netbox-census --out /home/dustin/nmas-probe-before.json
```

**Write that path down. Step 12 compares against it and nothing else can.**

**Proves:** what NetBox held before the probe, **by identity per type**, with
`nmas-managed` counted separately — because the population Remove may touch
is the tagged one, and a total that matches while the tagged set drifts is a
pass hiding a failure.
**If it fails:** stop. Without a baseline the teardown cannot be measured,
and the teardown is the point.

---

## Step 3 — boot an empty node

**SHARED — the containerlab host.**

```bash
cd ~/labs/bootstrap-probe
sudo containerlab deploy -t nmas-onboard-c.clab.yml
docker logs -f clab-nmas-onboard-c-bp-onboard-c 2>&1 | ts
```

Watch for `Startup complete`. Record how long it took.

**Proves:** a C8000v exists with **no startup config** — the wizard generates
the one it will boot with. Its own lab name, own network, own subnet, nothing
shared with `rcn-lab1`.
**If it fails:** stop, with the log. A node that fails to boot is a
containerlab problem, not an NMAS one, and diagnosing it here keeps the two
separate.

> **Per the D2 finding**, check uptime before trusting `Startup complete` — a
> vIOS took a CPU exception and silently reloaded while the container stayed
> healthy:
> `ssh admin@<mgmt-ip> 'show version | include uptime'`

---

## Step 4 — confirm NMAS sees nothing yet

**Local.**

```bash
curl -s localhost:5000/drift/status | python -m json.tool | grep -E 'inventory|checked'
```

**Proves:** the list is empty, so step 9's `N+1` has a known `N`.
**If it shows devices:** stop — you are not on the probe list.

---

## Step 5 — open the wizard

**Local. Creates nothing.**

Devices tab → **Onboard a device**. Enter:

| field | value |
|---|---|
| Name | `bp-onboard-c` |
| Platform | the C8000v entry (`cisco-ios-xe`) |
| Management IP | the node's clab management address |
| Management interface | leave blank — vrnetlab owns it on a C8000v |

**Proves:** the platform list offers the C8000v and shows the vIOS entry
**disabled with its reason** — stage D has not run, and an absent option
would teach you the tool does not support it.
**If the vIOS entry is missing rather than disabled:** that is a finding —
paste the platform list.

---

## Step 6 — ⛔ HARD STOP: read the review screen

**Local. NOTHING HAS BEEN CREATED. This is the last moment that is true.**

Do not press Create. Read:

- [ ] *"Nothing has been created yet. This is what will be."*
- [ ] **Every blocking reason**, if any — all of them at once, not the first
- [ ] the **NetBox objects** count
- [ ] **writes devices.csv: yes** (this is a `local` list)
- [ ] the **credential source**
- [ ] the **startup config** the node will boot with, and the note that the
      credential shown is a **placeholder** — the real one is minted at
      Create and never sent to the browser
- [ ] **Create is enabled**

Paste a screenshot or the review text.

**Proves:** the plan is computed and refusals are visible *before* anything
exists.
**If Create is disabled:** paste the reasons. That is the wizard working —
fix the reason, do not look for a way past it.
**If step 0 was skipped**, the reason you will see is *"NetBox writes are
disabled… the wizard will not turn it on for you"*.

---

## Step 7 — press Create

**SHARED — writes to the real NetBox.** Everything after this is recoverable
but not free.

The run order is fixed and each failure leaves a different, known state:

| fails at | what exists |
|---|---|
| credentials | nothing external; local and reversible |
| **netbox** | **no commit was created** — not a commit that was undone |
| commit | NetBox objects, tagged and recorded; Remove is offered |
| render | the device **is** onboarded; only the artefact is missing |

Paste the response.

**Proves:** the whole path, in the order 4C.3 pins.
**If it fails:** stop and paste. Do not press it again — a retry after a
partial run is a second run against a half-created device.

---

## Step 8 — inspect every artefact

**Local reads.**

```bash
# one commit, with its trailers
git -C data/lists/nmas-probe/config_repo log --format='%h %s%n%b' -1

# the identity was minted once
python -c "
import json;print(json.dumps(json.load(open('data/lists/nmas-probe/config_repo/.nsot/manifest.json')),indent=2))"

# committed intent exists
ls -la data/lists/nmas-probe/config_repo/host_vars/

# the CSV row (local list)
cat data/lists/nmas-probe/devices.csv

# the bootstrap credential was staged, and rotation cleared it
ls -la data/lists/nmas-probe/config_repo/.nsot/staging/credential/ 2>/dev/null \
  || echo "staging empty — rotation completed and cleared it"
```

**Proves:** **one commit**, one identity, intent committed, the CSV written,
and the staged credential **gone** — which is what rotation succeeding looks
like.
**If staging still holds a file:** rotation did not complete. The run should
have said `rotated: false` with a reason; if it claimed success and the file
is there, that is a finding and the more serious one.

---

## Step 9 — drift coverage

**Local.** Approvals tab → drift panel → **Check Now**.

**Proves:** `checked 1 of 1`. Before the first capture it reads **`0 of 1`
with `bp-onboard-c — no golden config saved` named on the panel**. Both are
correct; which you see depends on whether a golden was captured.
**If the device is absent from the counts entirely:** stop. That is precisely
the 3.3b failure — not an error, not a skip, *absent* — and it would mean the
population regressed to the legacy enumerator.

---

## Step 10 — the RW community

**Local read of the capture.**

```bash
grep -i 'snmp-server community' data/lists/nmas-probe/config_repo/golden/*.cfg
```

**Proves:** no `RW` community remains. vrnetlab nodes arrive with a
read-**write** `public`, removed during onboarding rather than after.
**If an RO community is present:** that is correct and expected — only RW is
removed, and over-broadening is the version that costs you monitoring.

---

# Teardown — this is a first-class step, and the part that has never run

Its acceptance is the census comparison, not "it looked clean".

## Step 11 — destroy the node

**SHARED — the containerlab host.**

```bash
cd ~/labs/bootstrap-probe
sudo containerlab destroy -t nmas-onboard-c.clab.yml --cleanup
docker ps -a | grep onboard-c || echo "gone"
```

**Proves:** no container, no veth, no leftover network.

---

## Step 12 — NetBox Remove, through the provenance path

**SHARED — deletes from the real NetBox.**

Preview first. It reports what it *would* delete and what it **skips as not
NMAS's**:

```bash
curl -s -X POST localhost:5000/netbox/safety/remove/preview \
  -H 'Content-Type: application/json' -d '{"list_name":"nmas-probe"}' \
  | python -m json.tool
```

**Read the skipped list before applying.** Remove deletes only the
intersection of *tagged `nmas-managed`* and *in NMAS's own record*; anything a
human curated is reported as skipped, and that claim is now being tested for
the first time.

Then apply, and compare:

```bash
curl -s -X POST localhost:5000/netbox/safety/remove/apply \
  -H 'Content-Type: application/json' -d '{"list_name":"nmas-probe"}' \
  | python -m json.tool

python scripts/nmas-netbox-census --compare /home/dustin/nmas-probe-before.json
```

**Proves — and this is the acceptance for the whole teardown:** `--compare`
exits **0**, meaning every counted type holds **exactly the objects** it held
before, **by identity**, with the `nmas-managed` set unchanged too.

**If it exits 1:** do not clean up by hand. Paste the output. It names the
type and the objects, and there are three distinct findings it can report:

- **left behind** — Remove did not delete something it created;
- **removed** — Remove deleted something that was there before, which is the
  worse failure;
- **the count matches and the objects do not** — something was created while
  something else was removed, which a count-only check would have called a
  pass.

---

## Step 13 — the local side

**Local.**

```bash
curl -s -X DELETE localhost:5000/device_lists/nmas-probe \
  -H 'Content-Type: application/json' -d '{"remove_from_netbox": false}'
ls data/lists/
```

`remove_from_netbox: false` because step 12 already did it through the
provenance path — the cascade is a different mechanism and running both would
make it impossible to say which cleaned up.

Then **turn step 0 back off**: Settings → Integrations → Allow writes to
NetBox → **off**. It defaults off and should end off.

**Proves:** `data/lists/` holds only the real lists.

---

## Step 14 — the secret check

**Local.**

```bash
python scripts/nmas-check-secret-storage
```

**Proves:** the one-time bootstrap credential left nothing behind, every
secret is where it should be, and every file holding one is owner-only.
**If it exits 1:** paste it. It reports by name and mode, never by value.

---

## What a full pass licenses

That **the wizard works end to end on a C8000v**, and that **Remove cleans up
exactly what it created** — measured by identity, not eyeballed.

It does **not** license: a vIOS (stage D has not run), a NetBox-sourced list
(a separate exercise with its own acceptance), or r6 (a real device on a real
topology, which is the next step and deserves its own checklist).
