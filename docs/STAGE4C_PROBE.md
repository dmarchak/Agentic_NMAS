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

### Method: every ACTION through the GUI; the shell only MEASURES

**Changed for the clean run, and the change is the point.** The first run
created the list with `curl`, and the API answered success while the
directory did not exist — harmless as it turned out, and it exercised none
of what a person uses.

**A curl-driven probe tests the functions underneath the tool.** That is a
different instrument from the one this probe exists to be: seven defects
tonight lived in the seams between correct parts — a renderer nothing
called, buttons that dropped a value they held, a payload of `{}` — and
every one of them is invisible to a request sent by hand, because sending it
by hand *is* supplying the wiring the tool was missing.

So:

| | |
|---|---|
| **In the UI** | anything a person does: creating the list, the Settings toggle, the wizard, Verify, Abandon, the NetBox Remove preview and confirm, deleting the list |
| **In the shell** | only reading state afterwards: the census, manifest and golden reads, `--compare`, the secret check — and the containerlab host, which is a different machine |

If a step below says "in the UI" and you cannot find the control, **stop and
record it**: a feature without a reachable entry point is the finding, not
an inconvenience to work around with `curl`.

### ⚠ Two names for this list, and the commands use different ones

The list is created as **`nmas-probe`**. Its directory is **`nmas_probe`**.

`config.list_slug()` replaces every non-word character with an underscore, so
the hyphen becomes one. **That means:**

| use the **name** `nmas-probe` | use the **slug** `nmas_probe` |
|---|---|
| every API call — `/device_lists`, the remove preview and apply | every **filesystem path** — `data/lists/nmas_probe/…` |

This is `ListRef`'s distinction showing up in a shell rather than in code:
*"`name` is what the operator sees, `slug` is the directory. They are
different strings and comparing one to the other is always false."* The type
makes that unrepresentable in Python; a runbook has no type, so it is written
down here instead.

**Found by running step 1.** Every filesystem path in the first draft used
the name and pointed at a directory that does not exist.

### What touches what

| | steps |
|---|---|
| **Local only** — NMAS host, nothing shared | 0, 1, 2 (reads NetBox), 4, 5, 6, 7, 9, 10, 13, 14 |
| **Shared: the containerlab host** | **3**, **11** |
| **Shared: the real NetBox — writes** | **8**, **12** |

Steps 8 and 12 are the only ones that change NetBox. Step 2 reads it.

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
print(staged_bootstrap_credential('data/lists/nmas_probe/config_repo','bp-onboard-c'))"
```

That is the whole point of staging it (4C.2): between the node booting with
it and rotation replacing it, it is the only way in. Recovering it is not
cleaning up — it changes nothing — so it does not break the rule.

---

## Where this probe stands — 2026-09-24 01:45

**Paused mid-run, deliberately.** The four remaining phase-2 steps are the
most consequential work of the stage — a device that rotates its own
credential and writes its first golden — and they deserve a session where a
mistake gets caught.

### The device

| | |
|---|---|
| `bp-onboard-c` | booted on `10.255.0.31`, holding the bootstrap credential |
| staged credential | present, and **matches** what the node booted |
| state | **promoted** (`verified_at` 01:38:33, CSV row exists) and **unfinished** |
| golden | none — no capture was taken |
| rotation | did not run; the device still holds the throwaway password |
| NetBox record | none; `netbox_id` is null |
| RW community | still present — there is no capture to remove it from |
| **CSV row** | exists with an **empty password**, so anything resolving through the inventory fails on a device that answers fine |

### Elsewhere

* Three NetBox scaffolding objects — region, site, VRF, all named after the
  list — created by the phase-1 import that could never have created the
  device. They are in the created-object record and are **step 12's** job.
* Census baseline: `/home/dmarchak/nmas-probe-before.json`.

### The state the design did not intend to exist

`promoted and unfinished` is reachable today only because promotion runs
**second** of three instead of last. Once the four steps land in the agreed
order — verify → capture → rotate (+record) → remove RW → save golden →
NetBox → promote — promotion happens only when everything before it
succeeded, and this state becomes unreachable.

**Two measured consequences of it, both worth fixing before the resume:**

1. **The banner will not offer Abandon for it.** `pending_devices()` skips
   any entry carrying `verified_at`, so the device is in no pending row and
   the button does not exist. The only path is `POST
   /onboard/abandon/bp-onboard-c` directly.
2. **`references()` does not check the CSV row.** It checks committed
   intent, the golden, NetBox and the credential override — so for a
   promoted device `release()` finds nothing and **hands the name back while
   the inventory row remains**. An inventory row for a device with no
   identity, no intent and no credential is the wrong-and-looks-right state,
   inside the flow written to prevent exactly that.

### The resume, when the four steps land

**Abandon → re-create → boot → verify**, so the whole phase runs as one
piece. Repairing this device in place would mean writing code for a state
the fix makes impossible, and the probe's value is proving what the code
does rather than patching what it did.

But **abandon should refuse a promoted device and say why**, rather than
learning to handle one: a promoted device is in the inventory, and removing
it is the existing delete path, not an onboarding undo. Which leaves
`bp-onboard-c` itself to be cleared by hand — and the probe list is
disposable, so deleting and re-creating the list is the cheaper answer than
teaching abandon a case that is about to stop existing.

### Two things that are easy to lose between sessions

**1. Step 12's Remove runs BEFORE the list is deleted, and that ordering is
the whole teardown's acceptance.**

Not a caution — the claim. The census baseline at
`/home/dmarchak/nmas-probe-before.json` is what proves Remove cleaned up
exactly what it created, by identity, and **a deleted list takes the
created-object record with it** (the record is keyed on the list slug).

Reversed, the three scaffolding objects become **tagged and unrecorded** —
the one combination Remove cannot act on, since it deletes only the
intersection of *tagged* and *in NMAS's own record*. They would then need
removing in NetBox by hand, and **the probe's central claim — that the
provenance-based Remove cleans up after itself — goes unmeasured.** That
claim is why the teardown is a first-class step and why the baseline was
taken before anything was created.

So: `--compare` first, then delete the list. Never the other way.

**2. The node stays running.**

`bp-onboard-c` on `10.255.0.31` is the reachable device the four remaining
steps are tested against — capture, rotation, RW removal and the golden all
need something that answers SSH. Rebuilding it costs a boot plus the
config-download-and-scp dance, for no gain: the device is fine, it is the
tool's record of it that is half-finished.

---

## Step −1 — retired, and what replaced it

**`scripts/nmas-verify-runbook` no longer applies to this file**, and its
refusal says so: *"only 1 command(s) found — the scan is not reading the file
it claims to read."* That floor is working. The runbook simply has almost no
`curl localhost:5000/…` lines left to check.

Step −1 existed because the runbook **drove the tool by curl**, and a wrong
path cost a sitting: two routes were reported missing by grepping the source,
when a blueprint's `url_prefix` is applied at registration and the full path
appears in no file.

With every action in the UI that hazard is gone, and a different one replaces
it: **a control that is missing, or present and wired to nothing.** No script
checks that — the probe does, which is the point, and the suite covers the
half it can (`test_blueprint_reachability.py` for the routes,
`test_onboard_wizard_renders.py` and `test_onboard_phase2.py` for the shipped
JavaScript, executed).

So the rule in **Method** above carries what step −1 used to: *if a step says
"in the UI" and you cannot find the control, stop and record it.* A feature
without a reachable entry point is the finding — three of tonight's seven
were exactly that.

`nmas-verify-runbook` stays for runbooks that are genuinely API-driven.

---

## Step 0a — ⛔ the census baseline, BEFORE anything can write

**Reads the real NetBox. Writes nothing. It is first because it can only be
taken first.**

```bash
python scripts/nmas-netbox-census --out /home/dmarchak/nmas-probe-before.json
```

**Write that path down. Step 12 compares against it and nothing else can.**

> **This step is not skippable, and it is not recoverable.** A baseline taken
> after the probe has begun writing contains **the probe's own objects**, so
> the teardown would measure clean while leaving them behind — worse than
> having no baseline at all. There is no moment after this one at which a
> truthful baseline can be taken.

**Measured on the clean run (2026-09-24):** this step was skipped. Creating
the list through the GUI does not prompt for a baseline, and the `--out`
command was lost when the method moved to the UI path. Step C's *onboarding*
was proven end to end and its **teardown could not be evaluated at all** —
the probe's central claim, unmeasured, on the run that otherwise passed.

**Do not proceed until the file exists:**

```bash
test -s /home/dmarchak/nmas-probe-before.json && echo "baseline present" \
  || echo "STOP — no baseline; step 12 cannot be evaluated"
```

**Proves:** what NetBox held before the probe, **by identity per type**, with
`nmas-managed` counted separately — because the population Remove may touch
is the tagged one, and a total that matches while the tagged set drifts is a
pass hiding a failure.
**If it fails:** stop. Without a baseline the teardown cannot be measured,
and the teardown is the point.

---

## Step 0 — enable NetBox writes, deliberately

**Local.** An explicit operator action, and the wizard will not do it for
you: a switch flipped as a side effect of confirming something else is not a
decision anybody made.

**In the UI.** Settings → Integrations → **Allow writes to NetBox** → on.

Then read it back, in the shell — the toggle is the action, this is the
measurement:

```bash
curl -s localhost:5000/settings/integrations \
  | python -c "import json,sys; print('netbox_allow_writes =',
      json.load(sys.stdin)['integrations']['netbox']['netbox_allow_writes'])"
```

The flag lives at `integrations.netbox.netbox_allow_writes` — **read from the
route, not inferred.** A `grep` would also match
`netbox_remove_on_list_delete` and tell you nothing about which is which.

**Proves:** the gate is open because you opened it.
**If it fails:** the wizard will name it as a blocking reason at step 6 — that
is the designed behaviour, not a problem to work around.

> **Leave it ON.** This instruction used to read *"turn it off again"*, and
> the reason was inherited rather than argued. Measured 2026-09-24: the gate
> was **on** throughout both NetBox incidents it would nominally have
> prevented, so it prevented neither. What caught them was the census
> baseline, the `nmas-managed` tag, the created-id record and `--compare`.
> Its real contribution is *"you turned it on deliberately once"* — a
> reminder, not a defence — and against that, ten devices are in NetBox and
> **every onboard needs it**, so off means the next one refuses at plan time
> until somebody remembers. Steady state is on.
>
> **What does not follow:** that writes are therefore covered. See
> [PHASE2_DHCP.md](PHASE2_DHCP.md) §11 — a **PATCH** is gated but carries no
> provenance and is invisible to `--compare`, which is the class that caused
> both incidents. The answer to that is to close the gap, not to keep a
> setting off that has to be on whenever the importer runs.

---

## Step 1 — a temporary list, not `default`

**In the UI.** Everything the probe creates lands in a repo that gets thrown
away.

Device List bar → **+ New List** → name it `nmas-probe` → create. Then
select it in the **Device List** dropdown, so every later step acts on it.

**Proves:** the list exists and is selected — the dropdown reads
`nmas-probe (0 devices)`.

**Not** `ls data/lists/nmas_probe`. The directory is created **lazily**, by
`get_list_data_dir()`'s `os.makedirs()` on the first write, so it does not
exist yet and its absence here is correct.

*(The first run created this with `curl` and asserted the directory. Both
were wrong in the same way: the API answered success, the directory was
absent, and nothing a person touches had been exercised.)*

**If it fails:** stop. Everything after this writes into that list.

---

## Step 2 — the baseline is already taken

Nothing to do here. It moved to **step 0a**, ahead of the first step that can
write, because that is the only point at which it is truthful — see the note
there.

Confirm the file is still where you wrote it down:

```bash
test -s /home/dmarchak/nmas-probe-before.json && echo "baseline present" \
  || echo "STOP — no baseline; step 12 cannot be evaluated"
```

*(This was step 2 on the first run, after the list was created. It stayed
skippable there, and on the second run it was skipped.)*

---

## Step 3 — prepare the clab host (no node is booted here)

**SHARED — the containerlab host.**

**The ordering inverted at 4C.8.** The node boots the config **the wizard
generates**, so the wizard runs first and the node is deployed at step 7b.
Step 3 is now everything that can be readied before either.

### 3a. Stage the launch patch

**Do not skip this.** The first attempt at step 3 did: the topology carried
no `binds:` line, the node launched *"with 1 SMP/VCPU"* on the stock script,
and at 112% CPU it ground for 25 minutes without reaching `Startup complete`
— the original bootstrap probe's failure, reproduced exactly.

```bash
cd ~/labs/bootstrap-probe
cp ~/labs/lab/patches/c8000v-launch.py patches/c8000v-launch-adopted.py

# Confirm it is the ADOPTED script, not the stage-A/B copy beside it.
grep -c 'smp="2"' patches/c8000v-launch-adopted.py                 # want 1
grep -c '_skip_users_defined_in_startup' patches/c8000v-launch-adopted.py  # want >= 2
diff patches/c8000v-launch.py patches/c8000v-launch-adopted.py
```

**Why a copy and not the path:** a throwaway lab whose teardown can reach
into production is not throwaway.

**Why it matters more than the vCPU:** without the skip, vrnetlab puts
`username admin privilege 15 password admin` ahead of the startup config,
IOS-XE refuses a secret for a user that already has a password, and the node
boots on `admin`/`admin` while the wizard's generated config says otherwise
— reporting healthy throughout. The probe would **pass** while producing the
exact hazard stage 2 exists to prevent.

**If the greps come back 0:** stop.

### 3b. Confirm `br-mgmt` exists and see what is on it

`br-mgmt` is a **prerequisite**, a Linux bridge on the clab host. Neither
this lab nor `rcn-lab1` creates it; both attach to it.

```bash
ip -br link show master br-mgmt
```

**Expect exactly two ports:** the host uplink to Proxmox `vmbr10`, and
`s3-mgmt`. The probe node becomes the **third device on that wire**,
alongside the NMAS and s3.

**If `probe-mgmt` is already there**, a previous run did not clean up. Stop
and say so rather than deploying over it.

### 3c. Measure what `--cleanup` does to a bridge node it did not create

**Before anything attaches to `br-mgmt`.** This is the one place the blast
radius is real, and "containerlab didn't create it, so it won't remove it"
is reasoning rather than measurement.

Measured on a **scratch bridge**, so `br-mgmt` is never exposed:

```bash
containerlab destroy --help | grep -B2 -A4 cleanup

sudo ip link add name br-probe-test type bridge
sudo ip link set br-probe-test up

mkdir -p ~/labs/cleanup-test && cd ~/labs/cleanup-test
cat > cleanup-test.clab.yml <<'YAML'
name: cleanup-test
topology:
  nodes:
    ct-host:
      kind: linux
      image: alpine:latest
    br-probe-test:
      kind: bridge
  links:
    - endpoints: ["ct-host:eth1", "br-probe-test:ct-eth1"]
YAML
sudo containerlab deploy -t cleanup-test.clab.yml
ip -br link show master br-probe-test

sudo containerlab destroy -t cleanup-test.clab.yml --cleanup
ip -d link show br-probe-test \
  && echo "SURVIVED - --cleanup is safe at step 11" \
  || echo "REMOVED  - drop --cleanup from step 11"

sudo ip link del br-probe-test 2>/dev/null
```

**Record the answer here when you have it, and make step 11 match it.** A
step that says "probably safe" is a step nobody can check.

---

## Step 4 — confirm NMAS sees nothing yet

**In the UI.** Devices tab with `nmas-probe` selected.

**Proves:** *"No devices saved yet"*, and **no pending banner** — so step 9's
`N+1` has a known `N` of zero, and any banner appearing later was put there
by this run.

**If it shows devices:** stop — you are not on the probe list.

---

## Step 5 — open the wizard

**Local. Creates nothing.**

Devices tab → **Onboard a device**. Enter:

| field | value |
|---|---|
| Name | `bp-onboard-c` |
| Platform | the C8000v entry (`cisco-ios-xe`) |
| Management IP | **`10.255.0.31`** |
| Mask | `255.255.255.0` |
| Management interface | **`GigabitEthernet2`** |
| Gateway | **leave blank** |
| Containerlab interface | leave blank — vrnetlab owns Gi1 on a C8000v |

**`10.255.0.31`, not `10.255.1.x`.** Verified free three ways on
2026-09-23: NetBox held exactly one address in that `/24` (s3's `Vlan99`),
no ping reply, and the neighbour table showed it `INCOMPLETE` with s3 the
only `REACHABLE` entry. `10.255.1.x` is a **loopback range reachable only
through OSPF** — free there and unusable.

**Gateway blank on purpose.** The NMAS is on this subnet and always
initiates, so the device needs no route to answer it. A default gateway
written when nothing needs one is a routing statement in a config whose
whole point is to have none.

**`GigabitEthernet2`, never Gi1.** vrnetlab owns Gi1. The wizard refuses to
default this field, and `test_probe_topologies.py` refuses a topology that
cables Gi1 — the same rule from both ends.

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

## Step 7b — ⭐ boot the node on the generated config

**SHARED — the containerlab host. This is 4C.8's acceptance.**

The wizard has produced a config. Nothing has booted it yet.

```bash
cd ~/labs/bootstrap-probe
# Save the wizard's artefact EXACTLY as downloaded. Do not edit it --
# the whole question is whether what the generator emits works.
cp ~/Downloads/bp-onboard-c.cfg configs/bp-onboard-c.cfg

grep -n 'ip address\|interface Gi\|router\|Loopback\|ip route' configs/bp-onboard-c.cfg
```

**Expect:** `interface GigabitEthernet2` with `ip address 10.255.0.31
255.255.255.0`, and **no** `router ospf`, **no** `Loopback0`, **no**
`ip route`. That is the shape `test_bootstrap_manager_address.py` pins;
seeing it on the real artefact is the point of looking.

```bash
sudo containerlab deploy -t nmas-onboard-c.clab.yml

# The bind took, before waiting out a boot:
docker logs clab-nmas-onboard-c-bp-onboard-c 2>&1 | grep -i 'SMP/VCPU'   # want 2

# The veth landed on the bridge:
ip -br link show master br-mgmt        # want probe-mgmt, plus the two from 3b

docker logs -f clab-nmas-onboard-c-bp-onboard-c 2>&1 | ts
```

Watch for `Startup complete` — expect **~6m30s**, the r1–r5 figure.

**Then check the username line was not rejected**, which is the stage-B
failure and is silent:

```bash
docker logs clab-nmas-onboard-c-bp-onboard-c 2>&1 | grep -i 'CVAC\|rejected'
```

Anything there means the user-skip did not fire and the node is on
`admin`/`admin` regardless of what the config says.

### The measurement

**From the NMAS**, not from the clab host — the clab host can reach the node
by paths the NMAS does not have:

```bash
ping -c3 10.255.0.31
ip neigh show 10.255.0.31          # want REACHABLE, with a MAC
ssh admin@10.255.0.31 'show version | include uptime'
```

**Proves what the whole of 4C.8 was about:** a config this program generated
makes a device the manager can reach. Every unit test passed before this was
true, which is why the acceptance is a socket and not an assertion.

**If ping works and SSH does not:** that is the interesting failure, not the
boring one — capture `show ip interface brief`, the `line vty` block and
`show ip ssh` from the console before changing anything.

**If ping does not work:** stop with `ip -br link show master br-mgmt` from
the clab host and `ip neigh show` from the NMAS. Do not start editing the
config on the device; the artefact is the thing under test.

---

> **Steps 8-10 read what step 7c produced.** They were blocked while phase 2
> was unwired; it is wired now, so they are measurements rather than
> aspirations. The old notice read:
>
> > ~~Steps 8-10 are BLOCKED on §8.6 of the Stage 4C plan.~~ Phase 2 —
> reach, capture, remove the RW community, rotate — is built and **not
> wired**: `finish_bootstrap()` has no production caller. So the staged
> credential will still be present, and there is no golden capture to grep.
>
> That is deliberate sequencing, not an oversight: phase 2 reaches a device,
> and it is being written after step 7b proves a generated config makes one
> reachable, rather than against the assumption that it does.
>
> **The probe stops at 7b for now.** Run the teardown (11-14) when you are
> done, or leave the node up if phase 2 is next.

## Step 7c — ⭐ Verify: the whole of phase 2, from the banner

**In the UI. This is the step the four new pieces exist for.**

Devices tab → the pending banner → **Verify now** on `bp-onboard-c`.

One click runs seven steps: **verify → capture → rotate (+record) → remove
RW → golden → NetBox → promote.** `ok` is true only if all seven ran.

**Proves** — and read the response, because each step reports separately:

- [ ] `verify` — the device answered, with `credential_source:
      device-override` (the credential onboarding staged, not one you typed)
- [ ] `capture` — a line count, not a handful
- [ ] `rotate` — the throwaway password replaced, and **recorded in the same
      act** to the override
- [ ] `remove_rw` — the RW community removed, the RO one **kept**
- [ ] `golden` — re-read after the removal and saved once
- [ ] `netbox` — the device created, now that there is something to import
- [ ] `promote` — **last**, and the only step that puts it in the inventory

**If any step fails**, the device stays **pending** with a named reason and
every step that did not run listed. That is the design: promotion is last,
so there is no path to a promoted device with the work unperformed — which
is exactly the state the first run reached.

**If it fails:** stop and paste the step list. Do not press it again — a
retry after a partial run is a second run against a half-finished device.

> **Its diagnosis is the thing to read on failure**, not the error string.
> A device that did not answer gets causes in the order they are worth
> checking, each with the console command that settles it, and the
> staged-credential recovery command with the real repo path.

---

## Step 8 — inspect every artefact

**Local reads.**

```bash
# one commit, with its trailers
git -C data/lists/nmas_probe/config_repo log --format='%h %s%n%b' -1

# the identity was minted once
python -c "
import json;print(json.dumps(json.load(open('data/lists/nmas_probe/config_repo/.nsot/manifest.json')),indent=2))"

# committed intent exists
ls -la data/lists/nmas_probe/config_repo/host_vars/

# the CSV row (local list)
cat data/lists/nmas_probe/devices.csv

# the bootstrap credential was staged, and rotation cleared it
ls -la data/lists/nmas_probe/config_repo/.nsot/staging/credential/ 2>/dev/null \
  || echo "staging empty - rotation completed and cleared it"
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
grep -i 'snmp-server community' data/lists/nmas_probe/config_repo/golden/*.cfg
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

**SHARED — deletes from the real NetBox. In the UI.**

> **Check the baseline first — before you press Remove.** Once the objects
> are gone there is nothing left to measure them against, and a teardown
> nobody can evaluate is this probe's central claim going unproven.
>
> ```bash
> test -s /home/dmarchak/nmas-probe-before.json && echo "measurable" \
>   || echo "STOP — no baseline; Remove will be UNMEASURABLE"
> ```
>
> If it is absent, **record the run as unmeasured** and say so in the notes.
> Do not take one now: it would contain the probe's own objects and report
> the teardown clean.

**NetBox tab** → find `nmas-probe` in the list → **Remove**.

That opens the safety modal, which runs a read-only dry run and shows every
object it *would* delete **and** every object it skips as not NMAS's.

> **Check the button is there first.** It renders only when the list has a
> sync summary. `nmas-probe` has one — phase 1's import recorded it — but if
> the button is absent, **stop and record it**: the teardown would have no
> UI path, and that is a finding rather than a reason to reach for `curl`.

**Read the skipped list before confirming.** Remove deletes only the
intersection of *tagged `nmas-managed`* and *in NMAS's own record*; anything
a human curated is reported as skipped, and that claim is being tested here
for the first time.

Expect **three** objects eligible: a region, a site and a VRF, all named
after the list — created by phase 1's import in the earlier run and left
behind deliberately. **No device**, because none was ever created there.

Confirm. The modal handles the one-shot token itself: the preview issues it,
the confirm consumes it, and the plan is recomputed — a changed plan is
refused with *"NetBox changed since preview"*, which is the recompute doing
its job rather than an error.

### Then measure, in the shell

```bash
python scripts/nmas-netbox-census --compare /home/dmarchak/nmas-probe-before.json
```

**This is the acceptance for the whole teardown:** `--compare` exits **0**,
meaning every counted type holds **exactly the objects** it held before, by
identity, with the `nmas-managed` set unchanged too.

**If it exits 2:** there was no usable baseline, and the run is **UNPROVEN**
— not passed and not failed. It says so in those words. Record it as
unmeasured; a baseline taken now would contain the probe's own objects.

**If it exits 1:** do not clean up by hand. Paste the output — it names the
type and the objects, and distinguishes three findings: something **left
behind**, something **removed** that was there before (the worse failure),
or **the count matching while the objects differ**, which a count-only check
would have called a pass.

---

## Step 13 — the local side

**In the UI, and in this order.**

1. **NetBox Remove has already run** (step 12). It must, because deleting the
   list takes the created-object record with it — the record is keyed on the
   list slug — and the three objects would become **tagged and unrecorded**,
   the one combination Remove cannot act on.
2. Device List bar → **Delete List** → confirm.
3. **Leave `netbox_allow_writes` ON.** Earlier revisions turned it off
   here. See step 0 for why that instruction was dropped: the gate was on
   through both incidents it would nominally have prevented, and every
   onboard needs it.

The delete does **not** cascade into NetBox unless
`netbox_remove_on_list_delete` is on — leave it off, because step 12 already
did the removal through the provenance path, and running both would make it
impossible to say which one cleaned up.

### Then measure

```bash
ls data/lists/
```

**Proves:** only the real lists remain.

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
