# Phase 2 — address from Kea. **Subject: a throwaway, not r6.**

**Decision, 2026-09-24.** Scoped against a new probe node. r6 is left alone.

---

## 1. What phase 2 proves, and who can prove it

`R6_PHASE1.md` states the variable outright:

> **anything about DHCP** — the address is static, from the config. That is
> phase 2, and phase 2 exists precisely to separate *"does the device fetch
> and apply"* from *"does the relay work"*.

That is an **onboarding-time** property: can a device be brought up and found
when its address is not written into the config that boots it. A throwaway
proves it completely.

**r6 cannot prove it, because r6 is already onboarded.** Running phase 2 on r6
would not be phase 2; it would be **re-addressing a managed device**, which is
a different capability:

| | phase 2 | re-addressing r6 |
|---|---|---|
| question | can a device be onboarded without a known address | can a managed device change its address and survive |
| subject | a node nothing depends on | the only device with a route the fleet learns |
| needed by | the wizard, for any site where addresses come from DHCP | nothing currently |

Re-addressing is a real capability and worth building **when something needs
it**. Nothing does. And it is not what the phase was scoped to demonstrate, so
doing it on r6 would spend the risk without buying the proof.

### The generalisation, because the phase numbering invited this

**A staged plan names the variable it changes and assumes the subject holds
still.** Phases 1/2/3 were defined as *"one further variable from phase 1"* —
which is only meaningful while the subject is where phase 1 left it. r6 has
moved: it now has committed intent, a golden, a route `r1` learns, and an
acceptance with a measured baseline. **Changing one variable from a different
starting point is a different experiment.** When the subject moves, the stage
is re-decided rather than re-run.

## 2. The rollback, which is the stronger argument

**r6's manager-facing address is the path every repair travels over.**

The change is `ip address 10.255.0.32 255.255.255.0` → `ip address dhcp` on
`GigabitEthernet2`. Traced through this tool:

* **It is expressible.** `merge_diff` sees `ip address dhcp` as a line to add;
  the static becomes a removal warning, and IOS replaces the address when the
  new form is applied. So merge-only *would* push it — this is not the wall
  option C hit.
* **The push succeeds.** The device accepts the command. What fails afterwards
  is *reachability*, if Kea does not answer inside the settle window.
* **And then the repair path is severed by the change itself.**
  `_capture_failure_state()` reads the device back over a **fresh
  connection**, and `rollback_commands()` restores the previous line by
  pushing it — both over the address that has just been given up. An
  unreadable capture is treated conservatively (*everything pushed is undone*)
  and the undo cannot be delivered.

This is the one change class where **the rollback travels over the thing being
changed**. Every other guard on the deploy path still applies and none of them
help: the confirm hash is correct, the program is merge-only, the credential
guard passes, the authorisation is unnecessary. The tool would do exactly what
it was asked, correctly, and lose the device.

Recovery is the console plus the break-glass record — which exists, is
verified for ten devices, and is the thing worth *not* needing.

**On a throwaway the same failure costs a `containerlab destroy`.**

## 3. Scope: phase 2 against a new probe node

Same pattern as the wizard's own proof, which ran on `bp-onboard-c` and not on
a fleet device. `br-mgmt` is proven, the teardown has run twice, and the
census baseline is step 0a.

| | |
|---|---|
| node | `bp-dhcp-a`, `cisco_c8000v`, its own `bp-dhcp-a.clab.yml` |
| launch patch | its **own** copy, staged per `STAGE4C_PROBE.md` §3a — never `~/labs/lab/patches/` |
| list | a temporary list, **not** `default` |
| bridge | `br-mgmt`, declared as a `kind: bridge` node owned by neither lab |
| address | none in the bootstrap config — that is the variable |
| teardown | census baseline at **step 0a**, before the first step that can write |

### What has to change in the tool, and it is the interesting half

`bootstrap_config.render_bootstrap()` raises `ManagementAddressRequired` when
given no address, and `build_plan()` makes that a **blocking reason** — by
design: *"a bootstrap config with no manager-reachable address is
unreachable… the device boots, reports healthy, answers its console, and
cannot be onboarded by anything."*

Phase 2 does not delete that rule. It adds the **one** case in which the
absence is not fatal: an address that will arrive from DHCP. So the wizard
needs a stated address **source**, not an optional address —

* `static` (today's behaviour, unchanged, still refusing an empty address);
* `dhcp`, which emits `ip address dhcp` on the manager-facing interface and
  requires the operator to name the pool or relay that will answer.

**A plain "address optional" checkbox is the wrong shape**: it turns a refusal
that exists to prevent a silent, healthy-looking, unreachable device into
something a person can switch off, and the two failures then look identical
from the wizard.

### What the probe must establish

- [ ] the node boots and obtains an address from Kea on `br-mgmt`
- [ ] the NMAS **finds** it — the wizard's pending banner resolves a device
      whose address it did not assign
- [ ] phase 2 of onboarding (verify → capture → rotate → remove RW → golden →
      NetBox → promote) completes against that address
- [ ] the address the tool records **is** the lease Kea issued, checked against
      Kea rather than against the device's own claim
- [x] ~~the lease is reserved, not dynamic~~ — **promoted to a precondition**
      and built: `build_plan()` asks Kea and refuses at plan time, with
      `unknown` (Kea unreachable) refusing as well, because a check that did
      not run has not passed
- [ ] teardown: census `--compare` clean, exit 0

### Explicitly out of scope

* **Re-addressing a managed device.** A separate capability, wanted by
  nothing today. If it is ever built, the design problem to solve first is the
  one in §2: a repair path that does not travel over the address being
  changed.
* **The relay** — phase 3, behind a switch. Phase 2 is L2-adjacent to the pool
  on purpose, so a failure means *"the device did not fetch"* rather than
  *"something between them did not forward"*.

## 3a. Built ahead of the probe, 2026-09-24

Runbook: **[PHASE2_PROBE.md](PHASE2_PROBE.md)**. Topology:
`docs/bootstrap-probe/nmas-dhcp-a.clab.yml`.


The tool half is done, so the probe measures the network rather than the code:

* `KeaIntegration.reservation_for(mac)` — `reserved` / `not_reserved` /
  **`unknown`**, via `reservation-get-all` where the `host_cmds` hook is
  loaded and `config-get` otherwise. Unreadable is never "no reservation".
* `OnboardPlan.address_source` (`static` | `dhcp`), `mgmt_mac`, and the
  reservation result carried on the plan.
* `blocking_reasons` refuses a DHCP device with no MAC, with no reservation,
  or whose reservation could not be checked.
* `manager_interface_lines()` emits `ip address dhcp` for the explicit
  sentinel; every refusal for a **missing** address is untouched for `static`.
* `OnboardPlan.address_claim` — the checkable sentence, in `summary`.

`tests/test_onboard_dhcp_source.py`, 23 tests, four negative controls.

## 4. What this leaves r6 as

The working branch site, untouched: committed intent, a golden, a `/32` the
fleet learns as extern 2 metric 20 from `10.255.1.23`, and a startup file that
survives a reboot. **Its acceptance stays a live regression check** — whatever
phase 2 does elsewhere, `r1` must still learn `10.255.1.16` in that exact
form.


---

## 5. Blocker: Kea serves no subnet for `br-mgmt` — and the answer is (a)

Measured on the deployment: Kea has `10.10.10.0/24` and `10.10.20.0/24`, each
with a pool, and **no subnet for `10.255.0.0/24`** — the segment the probe
node sits on. A node there gets no answer at all: no subnet, no pool, no
reservation. **Zero reservations exist anywhere**, so `reservation_for()`
returning `not_reserved` with `source: config` is the read path working
against an empty set — correct, and the probe will be its first real exercise.

### Recommendation: (a), reservations-only on `10.255.0.0/24`

(b) puts the probe on a segment with a pool **and a relay**, which is phase
3's shape. Phase 2's stated variable is *"same position, no relay, isolate
does-the-device-fetch from does-the-relay-work"* — and taking (b) means a
failure could be the device or the relay, which is the one distinction the
phase exists to make. The one-variable discipline is the whole reason the
phases are separate.

### Is a pool-less subnet legal in Kea? **Yes.**

`pools` is optional inside a `subnet4` entry. A subnet carrying only
`reservations` is a supported and documented configuration — it is how you get
*"nothing is addressed here unless it is explicitly reserved"*, which is the
right posture for a segment carrying the NMAS, s3's SVI and r6, all static. A
client with no reservation gets **silence**, not a wrong address.

One flag worth setting with it, and one worth checking:

* `"reservations-out-of-pool": true` on the subnet — an optimisation hint that
  reservations lie outside the pools. With no pool it is trivially true.
  Harmless either way; correct to state.
* **`authoritative`**, globally or on the subnet. If it is `true`, Kea sends
  DHCPNAK to a client asking for an address it does not know — so a device on
  `br-mgmt` that currently DHCPs and is *ignored* would start being actively
  refused. Today nothing there should be asking (r6's `Gi1` DHCPs on the
  **clab-mgmt** docker bridge, a different segment), but that is worth
  confirming rather than assuming, because the change turns silence into a
  refusal and the two look nothing alike from the client.

### The second missing piece is real: `interfaces-config`

**Kea answers only on interfaces it is told to listen on**, and it picks the
subnet for a directly-connected client from **the address of the receiving
interface**. So both of these have to hold and neither is implied by adding a
subnet:

```bash
# What Kea is listening on today
sudo kea-shell --service dhcp4 config-get 2>/dev/null \
  | python3 -c 'import json,sys; c=json.load(sys.stdin); \
      print(json.dumps(c[0]["arguments"]["Dhcp4"]["interfaces-config"], indent=1))'

# And that the host has an address INSIDE the new subnet on that interface
ip -br addr show enp6s19
```

If `interfaces` is `["*"]`, nothing to change. If it is an explicit list, the
`br-mgmt`-facing interface must be added — and it must carry an address in
`10.255.0.0/24` (the NMAS has `10.255.0.10/24` there), or Kea will not select
the new subnet for those clients.

### The edit

```json
{
  "subnet": "10.255.0.0/24",
  "id": 255,
  "interface": "enp6s19",
  "reservations-out-of-pool": true,
  "reservations": [
    { "hw-address": "<the probe node's MAC>",
      "ip-address": "10.255.0.40",
      "hostname": "bp-dhcp-a" }
  ]
}
```

No `pools` key. `"interface"` pins subnet selection to the segment rather than
relying on address matching alone, which matters on a multi-homed host.
`id` must be unique across subnets.

Then `sudo kea-shell --service dhcp4 config-test` before `config-reload`, so a
bad edit is refused rather than applied — the same shape as every dry-run in
this project.

### The MAC has to be DECLARED, not discovered

A reservation is keyed on the MAC the node presents, and a vrnetlab node's
data-interface MAC is assigned at boot unless the topology pins it. Discovering
it means: boot → read the MAC → write the reservation → reboot, and the node's
**first** boot is then a boot with no address, which is the state phase 2 is
supposed to be testing the absence of.

containerlab supports `mac:` per endpoint, so pin it in
`bp-dhcp-a.clab.yml` and write the reservation **before** the first boot:

```yaml
  links:
    - endpoints: ["bp-dhcp-a:eth2", "br-mgmt:bpdhcpa-mgmt"]
      mac: "aa:bb:cc:00:02:40"
```

Same rule as the management interface: **chosen, never defaulted.** A value
the tool needs in advance must not be something only the device can tell you
after it has already booted without it.

### What this adds to the probe's checklist

- [ ] `interfaces-config` includes the `br-mgmt`-facing interface, and that
      interface has an address in `10.255.0.0/24`
- [ ] `authoritative` is known, and the consequence of a NAK on that segment
      is understood before the subnet is added
- [ ] `config-test` passes before `config-reload`
- [ ] the MAC is pinned in the topology and the reservation written **before**
      the first boot
- [ ] after the run, `10.255.0.0/24` still has **no pool** — the posture is
      the point, not an accident of the probe


---

## 6. The Kea edit, exactly

Checks came back favourable: `interfaces-config` is `{"interfaces":
["enp6s19"]}` — already the `br-mgmt`-facing NIC, carrying `10.255.0.10/24` —
and `authoritative` is absent, so it defaults to **false** and an unreserved
client gets silence rather than a DHCPNAK. **The subnet block is the only
change.**

### 6.1 The MAC/address pair, written in both places at once

A MAC that differs between the topology and the reservation is a node that
boots and gets silence — and that failure **looks exactly like a Kea
problem**, which is the expensive way to spend an evening. So the pair is
chosen once and both files are written from the same variable:

```bash
MAC=aa:bb:cc:00:02:40      # locally administered; last octet mirrors the address
IP=10.255.0.40
echo "pair: $MAC -> $IP"   # paste this line into the runbook
```

The last octet of the MAC mirrors the host part of the address on purpose.
It buys nothing mechanically and makes a mismatch visible at a glance, which
is the only moment anyone will be looking.

### 6.2 ⚠ Pinning the MAC may not reach the client — verify, do not assume

**I cannot confirm from here that a containerlab-pinned veth MAC becomes the
MAC the IOS-XE DHCP client presents.** vrnetlab runs a VM behind the
container, and the address on `GigabitEthernet2` inside the VM may be assigned
by vrnetlab independently of the container's `eth2`. Treat the pin as
*probable, unverified*:

```yaml
# bp-dhcp-a.clab.yml — extended link format (containerlab 0.54+; check
# `containerlab version` first, the brief format has no per-endpoint mac)
links:
  - type: veth
    endpoints:
      - node: bp-dhcp-a
        interface: eth2
        mac: aa:bb:cc:00:02:40
      - node: br-mgmt
        interface: bpdhcpa-mgmt
```

**Verify before concluding anything about Kea**, on the booted node's console:

```
show interface GigabitEthernet2 | include bia
```

* matches the pin → the reservation is keyed correctly, proceed;
* **does not match** → the pin did not reach the VM. Read the real MAC, write
  *that* into the reservation, reload, and reboot the node. The first boot is
  then unaddressed — which is acceptable **because this is a throwaway** and
  is exactly why the subject is a throwaway. It would not be acceptable in
  production, and if the pin does not work that is a finding for the
  production story, not a detail of this probe.

### 6.3 The subnet block

Append to `subnet4` in `/etc/kea/kea-dhcp4.conf`. **Append, and give it an
explicit `id`** — see 6.5.

```json
{
  "id": 255,
  "subnet": "10.255.0.0/24",
  "interface": "enp6s19",
  "reservations-out-of-pool": true,
  "reservations": [
    {
      "hw-address": "aa:bb:cc:00:02:40",
      "ip-address": "10.255.0.40",
      "hostname": "bp-dhcp-a"
    }
  ]
}
```

No `pools` key — that is the posture, not an omission. `"interface"` pins
subnet selection to the segment rather than leaning on address matching alone,
which matters on a multi-homed host.

### 6.4 `config-test`, and telling a pass from a silent pass

Use the **offline** checker. It does not touch the running daemon, which is
the right property for a pre-flight:

```bash
sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf; echo "exit=$?"
```

Success is quiet — a short "syntax check OK"-style line at most — so **read
the exit code, not the output**. `exit=0` is the pass.

**Prove the checker can fail before trusting its pass.** A quiet tool and a
tool that did not run look identical, which is this project's most-repeated
lesson:

```bash
cp /etc/kea/kea-dhcp4.conf /tmp/kea-broken.conf
printf '%s' 'x' >> /tmp/kea-broken.conf          # deliberately invalid JSON
sudo kea-dhcp4 -t /tmp/kea-broken.conf; echo "exit=$? (expect non-zero)"
rm /tmp/kea-broken.conf
```

If the broken file also reports `exit=0`, stop — the checker is not checking,
and a pass on the real file means nothing.

### 6.5 Does a never-served subnet need more than `config-reload`? **No — with one caveat.**

`config-reload` re-reads the file the daemon was started with and reconfigures
in place; a new `subnet4` entry is picked up without a restart. `interfaces-config`
is unchanged here, so no socket needs re-opening — that is the case that would
have needed more, and it does not apply.

**The caveat is subnet IDs, and it is the one that can do damage.** Kea keys
leases by subnet id. If the existing two subnets have **no explicit `id`**,
Kea auto-assigns them by position — so inserting a subnet *before* them would
renumber them and orphan their leases. Two rules, both cheap:

```bash
# What ids exist today
sudo kea-shell --service dhcp4 config-get 2>/dev/null \
  | python3 -c 'import json,sys; \
      print([(s.get("id"), s["subnet"]) for s in \
             json.load(sys.stdin)[0]["arguments"]["Dhcp4"]["subnet4"]])'
```

* **append** the new entry at the end of the array, never insert;
* give it an **explicit** `id` well clear of the existing ones (`255`).

Use `config-reload` rather than the Control Agent's `config-set`: `config-set`
applies a configuration **without writing the file**, so the next restart
would silently lose the subnet — a change that works until the daemon
restarts and then does not, with nothing having said so.

```bash
sudo kea-shell --service dhcp4 config-reload
```

### 6.6 After the reload, before booting anything

- [ ] the new subnet is present **and the two existing ones are unchanged**,
      ids included — re-run the `config-get` above and compare
- [ ] `10.255.0.0/24` has **no** `pools` key
- [ ] `sudo kea-shell --service dhcp4 status-get` still reports the daemon up
- [ ] from the NMAS: `nmas` reports Kea green on the Monitoring panel
- [ ] the tool agrees — `KeaIntegration().reservation_for("aa:bb:cc:00:02:40")`
      returns `state: reserved, address: 10.255.0.40`. **This is the first
      time the reservation path has had anything to read on this deployment**,
      so a failure here is as likely to be the code as the config


---

## 7. What applying it taught, 2026-09-24

`reservation_for("aa:bb:cc:00:02:40")` → **`reserved` / `10.255.0.40`.** The
precondition path read a real reservation for the first time on this
deployment.

### It was applied by a RESTART, not a reload

Both reload routes failed:

| route | result |
|---|---|
| `systemctl reload kea-dhcp4` | *"Job type reload is not applicable"* |
| `kea-shell --service dhcp4 config-reload` | **HTTP 403** |
| `KeaIntegration.command("config-reload", service="dhcp4")` | `{"result": 1, "text": "service value must be a list"}` |

The 403 is the useful one: **the Control Agent is reachable and rejecting on
auth**, not down. `kea_username` / `kea_password` are unset, so the gap is a
missing credential rather than a missing capability — worth stating that way,
because *"the app cannot reload Kea"* invites someone to build a feature that
already exists.

**A restart re-reads leases from the lease file** rather than preserving them
in memory. Harmless here — nothing holds a lease on those subnets that matters
— and not a property to discover during a change that does.

### The client bug, fixed

Two faults in one call, and the second is the serious one:

1. `service` must be a list; a bare string gets `result: 1`. The settings
   default is already a list, so **every code path was correct and the first
   hand-typed call was not.**
2. `command()` returned `{"ok": True, …}` for any HTTP 200, so that refusal
   came back as a **success with the failure nested inside it.** `ok` now
   means Kea did the thing.

`result: 3` remains a success — it is *"worked, nothing to return"*, which is
`lease4-get-all` on an empty server. Making it a failure would have printed
*"v4: unavailable"* for an empty pool, so the fix for one half would have
introduced the absent-versus-empty error into the other. Both pinned.


---

## 8. Phase 2's variable is proven, 2026-09-24

```
device : GigabitEthernet2  10.255.0.40  YES DHCP  up/up
         bia aabb.cc00.0240          <- the pinned MAC IS what the VM presents
wire   : DISCOVER + REQUEST from aa:bb:cc:00:02:40, both answered by 10.255.0.10
Kea    : lease 10.255.0.40, hostname bp-dhcp-a, subnet-id 255, valid-lft 3600
NMAS   : pings it, 0.58 ms
```

**The device fetches and applies with no relay in the path** — which is exactly
what phase 2 was scoped to separate from phase 3. And the *first DHCP
transaction that segment has ever carried*, against a reservation-only subnet
with no pool.

**The MAC pin is now measured rather than probable.** `nmas-dhcp-a.clab.yml`'s
warning and the fallback it described can stand as history: containerlab's
per-endpoint `mac:` survives vrnetlab's VM, so a reservation can be written
before a node's first boot.

### What step 9 needed before it could run

The tool never wrote this address, so phase 2 has to **discover** it — and
three places assumed it had not had to:

| place | what it did | what it does |
|---|---|---|
| `verify_device()` | read `mgmt_ip` from the manifest — empty by construction | discovers it from **Kea's lease** |
| `run_phase_two()` | kept its own local `mgmt_ip`, so six later steps used `""` | adopts what verification used |
| `bind_credentials_step()` | keyed the override on `plan.mgmt_ip` — the empty string | keys it on the **reserved** address |

**The lease, never the reservation**, and a disagreement between them refuses
and names both. The reservation is what the address was *meant* to be; the
lease is what the device *has*. Picking one would put an address into the
inventory that another store contradicts — the failure the reservation
precondition exists to prevent, arriving one layer down.


### The one finding in the census, and it is fixed

NetBox recorded the leased address as a **host route** for an interface that is
really on a /24. The mask is not in the manifest for a DHCP device — correctly,
it is not known at plan time — so `_upsert_device`'s last resort applied, which
exists for a golden that genuinely has no addresses (and a DHCP golden says
`ip address dhcp`, so it has none).

**The lease knows.** It carries a `subnet-id`, and the server's own
configuration has the CIDR. Threaded:

```
KeaIntegration.lease_for()        -> prefix_length, from subnet-id via config-get
discover_dhcp_address()           -> carries it
verify_device()                   -> reports it, and names it in address_note
manifest                          -> mgmt_prefix_len
create_netbox_record()            -> prefix_len on the device dict
_upsert_device()                  -> f"{ip}/{prefix or 32}"
```

**Unknown stays 0, never 32**, and the host-route fallback survives with a test
asserting it: a golden with no addresses tells nobody the subnet, and a host
route is the honest answer there. Guessing in the new code would have moved the
defect rather than removed it.

Being wrong about the network is the one thing NetBox cannot be, because that
is what NetBox is for.


## 9. Phase 2 is closed, 2026-09-24

**A device the tool never addressed.** That is the whole claim, and every word
of it is measured:

| | |
|---|---|
| the tool wrote no address | `build_plan()` drops `mgmt_ip`/`mgmt_mask` when `address_source: dhcp`; the bootstrap config says `ip address dhcp` |
| the device fetched its own | DISCOVER + REQUEST from `aa:bb:cc:00:02:40`, both answered; `GigabitEthernet2 10.255.0.40 YES DHCP up/up` |
| from a **reservation**, on a pool-less subnet | the first DHCP transaction that segment has ever carried |
| the tool **found** it by asking Kea for the **lease** | `discover_dhcp_address()` reads `lease4-get-all`, never `reservation-get-all` |
| then reached, captured, rotated, cleaned, recorded, promoted | phase 2's seven steps, promotion last, unchanged |
| the **leased** address is what was recorded | manifest, `devices.csv`, NetBox and Kea all say `10.255.0.40` |
| a disagreement refuses rather than picks | `discover_dhcp_address()` names both operands and returns no address |

### The lease, never the reservation — and why that is the load-bearing line

The reservation is what the address was **meant** to be. The lease is what the
device **has**. They agreed here, so nothing distinguished them at runtime and
the choice is invisible in the result — which is exactly why it had to be made
before the probe rather than after it.

A tool that reads the reservation is reading **its own intent back** and calling
it a discovery. It would report an address for a device that never booted, for
one that booted on a different interface, and for one whose reservation was
edited after the lease was granted. **A lease is a fact; a reservation is
intent** — the same distinction as a golden config against a render, and the
same rule: never substitute one for the other because they usually agree.

So a disagreement is a **refusal naming both**, not a preference. Picking either
would put an address into the inventory that another store contradicts, which is
the failure the reservation precondition exists to prevent, arriving one layer
down where nothing was watching for it.

### What phase 2 does not prove

Reboot-safety. The probe node was destroyed, not rebooted, and a DHCP-addressed
device's startup config is a separate question from its running one — `§11` of
the runbook says so deliberately. Nor does it prove a **relay** path, which is
phase 3: the NMAS shares the segment here and always will on `10.255.0.0/24`.
Isolating those was the point of doing this on a throwaway.

### The teardown, which is the part that is usually assumed

- `nmas-netbox-census --compare` → **exit 0**: NetBox holds what it held before,
  **by identity** — including through the VRF/site/region deletes that took
  r3's addresses the previous time, which are the unmeasured edges in the
  cascade map
- `br-mgmt` holds `uplink`, `s3-mgmt`, `r6-mgmt` and no `dhcpa-mgmt`; docker
  networks are `clab` and `clab-r6`
- the temporary list is gone; `netbox_allow_writes` is left **on** (§11)
- Kea: reservation removed, pools still **0**, `config-test` 0, reload
  successful, `_reservation()` back to `not_reserved`
- **r6 regression**: `r1` still learns `10.255.1.16` as extern 2, metric 20,
  from `10.255.1.23`, six hours old. The probe touched nothing of r6's
- `nmas-credential-overrides` flagged `10.255.0.40` **ORPHAN** the moment its
  list stopped existing

That last one is the survey's first real case and it is worth naming: the
r6-era residue we cleaned by hand would now be **reported** rather than
accumulate. A secret store with no expiry and no owner check does not need a
reaper so much as it needs somebody able to answer *"which of these
corresponds to a device that exists"* — and now something does, every run.


## 10. The defect ledger, because it is the argument for the method

**9 commits fixed things found by running the tool** (11 in the stage; two are
probe authoring, before any node booted). Those 9 carry **15 distinct
defects**. The suite was **green at every point**, 3,276 → 3,360 tests, and its
assertions were exact.

| # | defect | site | age |
|---|---|---|---|
| 1 | `command()` reported `ok: True` wrapped around Kea's own `result: 1` — a refused `config-reload` read as applied | `integrations/kea.py` | Phase 0, 4d |
| 2 | the Gi1 management check matched one spelling, blind to the extended link format the MAC pin needs | `test_probe_topologies.py` | 1d |
| 3 | the probe's management subnet collided with r6's running lab | `nmas-dhcp-a.clab.yml` | today |
| 4 | the wizard had no address-source control and no MAC field: the server read fields no form sent | `partials__onboard_wizard` | today |
| 5 | `bootstrap_artifact()` judged completeness by the static shape, so a DHCP device's **expected** absent address drew the legacy "no address recorded" refusal | `nsot/onboard.py` | today |
| 6 | the pending row rendered `at —` for an address that is not knowable yet | `partials__onboard_pending` | today |
| 7 | `verify_device()` read `mgmt_ip` from the manifest — empty by construction | `nsot/onboard.py` | 1d |
| 8 | `run_phase_two()` kept its own local `mgmt_ip`, so six later steps used `""` | `nsot/onboard.py` | 1d |
| 9 | `bind_credentials_step()` keyed the staged override on `""`; `resolve()` fell through to `profile:default` and the device refused it | `nsot/onboard.py` | today |
| 10 | the failure never mentioned `credential_source`, which was the diagnostic that solved it | `nsot/onboard.py` | 1d |
| 11 | the wizard's reveal ran on `change` only, so a remembered `dhcp` displayed the static fields — **second use only** | `partials__onboard_wizard` | today |
| 12 | a torn-down device's address sat pre-filled in Management IP | `partials__onboard_wizard` | today |
| 13 | abandon cleared `mgmt_ip`'s key and not `reserved_address`'s, so the credential outlived the device | `nsot/onboard.py` | today |
| 14 | `nmas-credential-overrides` could not reach its own imports | `scripts/` | today |
| 15 | NetBox recorded the leased address as a **/32** where the interface is a /24 | `netbox_client.py` | **5 months** |

**9 of 15 were written today**, 4 yesterday, 1 four days ago, 1 five months
ago. **None of the 15 was caught by the suite** — not one, at any point.

### Why not one, stated precisely enough to be actionable

Every one lives in a **seam**: between the form and the server (4, 11, 12),
between a value and the store it is keyed in (9, 13), between the tool and a
service (1, 15), between a function and the caller that no longer supplies what
it reads (7, 8), between a check and the spelling it was pointed at (2), between
a message and the state that actually occurred (5, 6, 10), between a script's
entry point and its imports (14), and between the repository and a constraint
that lives in a running daemon (3).

**A test that constructs its own subject cannot notice that the caller does
not.** That is now the dominant class in this project — this stage takes it to
nine instances — and the mechanical responses are the ones that have worked:
`test_server_reads_nothing_the_form_cannot_send.py` (one list, read by both
ends), the entry-point sweep, `assert_dialect()` at a boundary, and executing
the **shipped** renderer against the payload the **deployed** endpoint returns.

### What the suite did do, which is not discovery

It made every one of those 15 fixes **safe to make**. Three regressions I
introduced while fixing them were caught immediately and by name — the
forward/rollback consistency assertion, the duplicated stanza header, and a
stub that had stopped matching its subject. One of my own two errors in the
final commit was caught by the suite (`test_no_ip_literals`, on a **comment**);
the other, a `NameError` from an inferred signature, was caught by running.

So the honest division of labour, and it should be stated this way rather than
as scepticism about tests: **running the tool is how defects are found; the
suite is how they stay fixed.** A stage that only runs the suite discovers
nothing, and a stage that only runs the tool goes backwards while it works.


## 11. `netbox_allow_writes` stays ON, and a gap the decision exposed

Both probe runbooks said *"turn it off again at teardown"*. Neither said why,
and an instruction whose reason is *"that is what the last one said"* is one
nobody can evaluate — so it is either justified here or dropped.

### It is dropped, and the measurement is why

The gate is a real control: it means *"this instance may write to NetBox at
all"*, it defaults off, and it is a persistent operator decision. But it
prevented neither of the two NetBox incidents, because **it was on throughout
both** — it has to be, or the import that caused them could not have run. What
caught them was the census baseline, the `nmas-managed` tag, the created-id
record, and `--compare`.

So its contribution on this installation is *"you turned it on deliberately
once"*: a reminder rather than a defence. Against that, ten devices are in
NetBox and **every onboard needs it on**, so off means the next onboard refuses
at plan time until somebody remembers — friction guarding a hazard the real
defences already cover.

**Steady state is on.** It stays a persistent, deliberate decision; it is
simply one that has been made.

### The case worth checking, and it exists

*"Is there anything that writes to NetBox without going through the provenance
path?"* Measured, in two parts.

**Nothing writes outside the gate.** There are exactly **three** HTTP write
calls in the whole codebase — `session.post`, `session.patch`,
`session.delete` — each inside its chokepoint, each behind
`assert_writes_allowed()`. Grep the tree for a fourth and there is none.

**But `_nb_patch` is outside the PROVENANCE path**, and that is a different
claim:

| | `_nb_post` | `_nb_patch` | `_nb_delete` |
|---|---|---|---|
| gated on `netbox_allow_writes` | yes | yes | yes |
| previewed in dry run | `creates` | `updates` | `deletes` |
| tagged `nmas-managed` | yes | **no** | n/a |
| recorded in `netbox_created_ids.json` | yes | **no** | forgotten |
| reversible by Remove | yes | **no** | n/a |
| visible to `--compare` | yes | **no** | yes |

The last row is measured, not reasoned. The census identity is
`f"{id}:{display}"`, and moving an address between interfaces changes neither:

```
identity before : 41:10.0.0.15/24
identity after  : 41:10.0.0.15/24
compare() findings: NONE
```

**That is exactly the 2026-09-24 damage** — *"one object passed between six
devices"* was `_ensure_ip_address()` PATCHing `assigned_object_id`. The object
never disappeared, so the census had nothing to report, and Remove could not
have undone it because an update is not a creation.

Not tagging an update is **correct**: the tag means *NMAS created this*, and
tagging something it merely touched would claim ownership of a human's object
and make it deletable. The gap is not the missing tag, it is that **nothing
records the touch at all.**

Eleven PATCH call sites, and one shows the shape plainly — `_ensure_site()`
re-parents any site whose slug matches, with the comment *"re-parent to the
right region if someone moved it"*. It is deliberately overriding a human's
change, on an object provenance explicitly does not cover, and Remove
correctly reports as skipped. Nothing anywhere records that it happened.

### Why this does not change the decision

It reads like an argument for off, and it is not, for one reason: **the gate
must be on for the importer to run at all.** Both incidents happened with it
on, and the next import will too. A control that is necessarily open whenever
the dangerous path executes is not a defence against that path — turning it
off at teardown does not cover the uncovered class, it only makes the next
onboard refuse once.

So: leave it on, and **close the gap instead of keeping a setting off that has
to be on.** The shape is the same finding as the cascade, one field over:
*provenance protects an OBJECT; a cascade travels a RELATIONSHIP* — and an
**update travels neither.**

## 12. The modification record — built

`data/netbox_modified.json`, written by `_nb_patch`, read by the census.

### Where it lives: a second file, and that is the whole point

Not the created-id record. That record means *"NMAS created this"* and is one
half of removal's `tagged AND recorded` test — so putting an update in it
would mark a human's object as NMAS's own and **make it deletable**, which is
precisely the ownership claim an update must not make. Two files means *"what
has NMAS touched here"* is answerable without being confusable with *"what may
NMAS remove"*. Pinned: after recording a modification,
`was_created_by_nmas()` is still false and `get_created()` is still empty.

`forget_created()` — what deleting a list does — leaves the modification
history intact. Otherwise the trail would be erasable by the routine action
that follows every probe.

### What it stores, and why the BEFORE is the load-bearing half

`{endpoint, id, name, fields: {field: {before, after}}, actor, at}`.

*"NMAS set `assigned_object_id` to 60"* is a fact. *"NMAS moved it from 44 to
60"* is the finding — so the before-state is **read by `_nb_patch` itself**,
immediately before the write. Not passed in by the caller: an optional
`before=` is how a caller bypasses a guard by omission, and there are eleven
PATCH call sites.

Three states rather than two, throughout:

| situation | recorded |
|---|---|
| a field's value changed | `{before, after}` |
| every field already held that value | **nothing** — the object's content did not move |
| the object could not be read first | `before_unknown: true`, counted separately |
| a field NetBox did not return | `before: "<unknown>"`, distinct from a genuine `null` |

Values are capped at 200 characters **with a marker**, because *bulk is not
evidence* — the `skipped_drifted` entry carried a whole device config and
neither of the two hashes it had compared.

NetBox's nested form is normalised before comparing: a GET returns
`{"region": {"id": 5, …}}` and a PATCH sends `5`. Without that, every field of
every PATCH looks changed, the log records a modification on every no-op sync,
and it stops meaning anything — which is how a checker gets switched off.

### What reads it: the census, and PASS now states its claim

A record nothing reads is the `next_ts` shape, so this is the part that
matters. `--compare` prints a modifications line and **says which claim it is
making**:

> THE CLAIM THIS MAKES: no object was created or destroyed. It does NOT say
> nothing changed — an in-place update changes neither an object's id nor its
> display, so this comparison cannot see one.

The headline is qualified — `PASS (with modifications — read them above)` —
because a reader skimming for the word PASS will not read the paragraph under
it. **Exit codes are unchanged**: a modification is not *"objects left
behind"*, and collapsing them would repeat the error the three codes exist to
avoid.

**Four states, not two**, because a zero must not pose as an assurance:

| status | means |
|---|---|
| `none` | 0 since the baseline, *out of N recorded in total* — the denominator is what proves the recorder runs |
| `some` | N modified, each listed with its before → after |
| `unknown` | the record could not be read — *"weaker than 'none', not equal to it"* |
| `no-record` | the file has never been written; on an install that has run an import, **the recorder is not reaching it** |

The headline is selected from that status and **never by matching the printed
sentence** — the first version did, which is the *pattern that can appear in
English* error committed inside the fix for it, and it also read `unknown` as
*"modifications exist"*.

Scoping is honest too: a baseline with no `taken_at` cannot scope the count,
so the line says **"all time — could not be scoped to the run"** rather than
attributing old modifications to this teardown.

### `_ensure_site()`: a behaviour nobody chose

It re-parented any site whose slug matched, with the comment *"re-parent to
the right region if someone moved it"* — so a site a human had deliberately
placed was silently moved back on the next sync. Inconsistent in the direction
that matters: **removal refuses to touch an object NMAS did not create**, so
the tool would decline to delete your site while happily moving it.

It now re-parents only its own, and **reports** when it declines — collected
into the sync summary's `notes`, not only logged, because a refusal nobody
reads is the same as no refusal. Adoption is unchanged: a matching site is
still used rather than duplicated. What changed is that it is no longer edited
silently.

Ownership here is **tagged OR recorded**, deliberately *not* removal's `tagged
AND recorded`. The actions differ in blast radius — deleting a human's object
is unrecoverable, so removal takes the conservative conjunction, while
declining to re-parent NMAS's own site costs a warning. The tag is applied by
`_nb_post` only, so a tagged site *was* created by NMAS even if the created-id
record has since been lost, which is what happens when a list is deleted and
re-created.

### Also fixed on the way

Both provenance records are now written **temp-then-`os.replace`**. They were
`open(path, "w")` — truncate in place, the shape that erased
`user_settings.json`. A fragment of either reads as **empty**, and for the
created-id record that means Remove can no longer find objects it created:
they become *tagged and unrecorded*, the one combination it cannot act on.


## 13. The recorder's first run found three things, and one was the recorder

Measured on the live NMAS, first sync after §12 shipped.

**Two genuine findings, which is the mechanism working.** `prefixes
55:10.255.1.16/32` — r6's loopback, created since the baseline, reported by
the census. And the sync rewrites `local_context_data` wholesale, so the
before/after showed r2's stored running config moving from an **August**
capture to today's: NetBox had been holding a month-stale full config copy and
the sync refreshed it. Worth knowing on its own, and nothing would have said so
before.

**And the recorder was the third.** 113,767 bytes from one sync of ten
devices, because `local_context_data` is a **dict** holding a whole running
config, and the cap was on **strings**. Two costs beyond the size:

- **It stored credentials.** The after-value carried a device's
  `secret 9 $9$…` and a `username … password 0` line, unmasked, in
  `data/netbox_modified.json`. *A new place a device credential lives,
  created by the fix for a provenance gap* — and
  `nmas-check-secret-storage` did not know about it, which is **verbatim its
  own warning**: *a secret in a store this script does not know about is not
  reported at all*, arriving in a store created after the warning was
  written.
- **A record that costs 113 KB a sync is one somebody turns off** — the same
  end as the drift checker, reached by volume instead of noise.

### Measured by size, never by type

`record_value()` serialises first and caps on **that**, so a dict, a list and
a string are all subject to the same limit. Over it, the record is
*changed, this big, this hash*:

```
local_context_data: 14.2 KB → 15.1 KB (sha 3f2a1c4b8e91 → 9c81d0f2a7b3)
```

That **is** the finding. The bytes are not — the same lesson as
`skipped_drifted` carrying a whole device config and neither of the two hashes
it had compared.

**The hash is of the raw value, deliberately.** Hashing the masked form would
make a credential rotation hash-identical to no change at all: the one
movement most worth noticing, rendered invisible by the masking meant to
protect it. A truncated digest of a multi-kilobyte config is no practical
oracle, and a value short enough to be guessable never reaches that path — it
is under the cap, so it is redacted and stored instead.

### Masked on the way in, and failing closed

Everything recorded goes through `redact_text()`, the same redactor a golden
gets on the way out — **positional as well as value-based**, so a device NMAS
has never been told about is covered too.

It **fails closed**, which is the opposite of the log filter and deliberately
so. A log that silently loses entries is the worse failure in the file an
operator reaches for when something has already gone wrong; **nobody diagnoses
an outage from the modification record**, so a dropped value costs a detail and
a leaked one costs a credential. When redaction cannot run, the record says
`<unredactable — not recorded>`.

Note what is *not* claimed: a `$9$` value is a salted hash, not a recoverable
password, and it is already in `golden/` verbatim by design — *masking is
outbound, never at rest*, because a golden has to restore a network. **That
argument does not extend to an audit record**, which nobody restores anything
from, so this one is masked at rest. The `password 0` form is a plaintext
credential outright.

### What was already on disk

Fixing the writer does nothing about what is written, and *a tightened mode
does not undo exposure* applies to a record as much as to a file.
`scripts/nmas-netbox-modified --sanitise` rewrites the existing record through
today's summarisation and masking, **keeping both findings** — it is the
content of oversized fields that goes, replaced by the size and hash of each
side.

Both provenance records are also now created `0600`, and a loose mode
**self-heals on the next write**: `os.replace` swaps in the temp file's inode,
so the mode it was created with becomes the record's. Measured — the checker
found `netbox_created_ids.json` at `0664` on the dev checkout, from before
`open_secure` was applied.

### On the live host

```bash
python3 scripts/nmas-netbox-modified --sanitise   # then:
python3 scripts/nmas-check-secret-storage         # must report no secret-shaped content
```


## 14. The record's first real finding: NetBox says s1 is offline, and it is not

Found by the modification record on its **first live run**, 2026-09-24.
`dcim/devices` for s1: `status: active → offline`, while s2, s3 and s4 stayed
active in the same sync. Measured afterwards on the device itself: s1 answers
SSH and returns its running config. **The source of truth holds a false
statement about a device that is up.**

### 1. What the sync sets `status` from — measured

`_sync_list_to_netbox_impl`, at the `_upsert_device` call:

```python
status="active" if (status_cache or {}).get(result["ip"], False) else "offline"
```

`status_cache` is `app.device_status_cache`: an **in-memory dict** written by
`connection.ping_worker`, a background thread that every **5 seconds** calls
`is_device_online(ip)` — ICMP via `ping3`, falling back to a TCP connect to
port 22. So it is a **live reachability probe**, not derived from anything
else, and what lands in NetBox is *whether one ICMP or TCP attempt succeeded
within 5 seconds of the sync*.

Driven through the real function, the status that reaches the wire:

| cache state | status written |
|---|---|
| pinged, answered | `active` |
| pinged, did not answer | `offline` |
| **never pinged (key absent)** | **`offline`** |
| **cache empty or absent** | **`offline`** |

The bottom two rows are the defect this project has already named: *a lookup
that misses is a fact about the query, not about the system.* `.get(ip,
False)` cannot tell **"probed and failed"** from **"never probed"**, so the
two states most different in meaning share an answer — and the answer is the
assertive one.

Three ways to be never-probed, none of them exotic:

- the ping worker reads `_get_current_devices_file()` — **the active list
  only**. Syncing any other list marks every device in it offline.
- a NetBox-sourced list has no CSV, so `os.path.exists(fn)` is false, `devices`
  stays `[]`, and **nothing in that list is ever pinged**.
- the first cycle has not completed yet; a sync in that window marks
  everything offline.

None of those explain s1, and that is useful: **s2–s4 staying active rules the
structural causes out** and leaves a genuine transient — one ICMP/TCP attempt
that did not answer at 05:22.

### 2. What reads it — and the answer is worse than "a human might"

`modules/inventory/source_config.py`, the default filter for a **NetBox-sourced
list**:

```python
"filters": {"site": "", "role": "", "tag": "", "status": "active"},
```

passed straight into the device query. So on a NetBox-sourced list:

1. one failed ping writes `status: offline`
2. the next inventory refresh queries `dcim/devices/?status=active`
3. **s1 is not returned — absent, not skipped, not named**
4. everything keyed on the inventory stops covering it: polling, backups,
   drift, the pool, bulk ops, deploy targets
5. and the next sync iterates **the inventory**, which no longer contains s1,
   so nothing ever sets it back

**Self-sealing.** The state that removes a device is the state only that device
being present could correct. It is the *"absent, not an error, not a skip"*
shape with a feedback loop attached.

**It is not firing today**, and the reason is luck rather than design: `default`
has no `source.json`, so it is `local` and the inventory comes from the CSV.
The loop arms the moment a list is switched to `netbox` — which is the whole
point of Phase 1.

Outside NMAS, anything the operator has pointed at NetBox — a Grafana panel, an
Ansible inventory, netbox-agent — reads the same field. That is beyond what can
be measured from here, and worth checking against whatever else consumes it.

### The recommendation: stop writing it, and the project's own rule says why

Not *"NetBox isn't a monitoring system"*, though it is not. The stronger
argument is already written down here, as the reason
`netbox_client._scan_device` was **deleted**:

> importing observed state into the source of truth is the wrong direction

A ping result **is** observed state. That rule removed 140 lines of SSH
scanner, and this one field survived it by being three words on a call site
rather than a function with a name.

Precisely:

- **create** may set `status: active` — a claim about lifecycle, and onboarding
  has reached the device before the record exists, so it is earned
- **update** must drop `status` from the PATCH allowlist entirely, leaving
  whatever a human set

Liveness already has an honest home: the app's own online/offline badge, driven
by the same cache, live at the moment it is read, and which nobody mistakes for
a stored fact. The middle option — write only on a confirmed transition, with
`inconclusive` distinct from `offline` — is defensible and still writes a
liveness fact into a store whose other fields describe intent.

**Not applied here.** It changes what the tool asserts about the network and is
the operator's decision.

### 3. What the record bought, on day one

`--compare` said *no object was created or destroyed*, and **that was true**.
The drift checker compares device configs, not NetBox fields. The census
compares identity, and an in-place status change alters neither an object's id
nor its display. Nothing else looks.

So a false statement sat in the source of truth, and **the only thing in the
system that could see it was the record built the day before** — which found it
on its first real run, in a field nobody had thought to check, about a device
nobody had reason to suspect.

That is the argument for the record existing, made by the record rather than
about it.


## 15. Applied: the sync no longer writes status, and the sweep that followed

### The change

- **`status` is gone from the PATCH allowlist** in `_upsert_device`, and the
  inline `"active" if (status_cache or {}).get(...) else "offline"` is gone
  from the call site — the expression, not just its effect.
- **Create still sets `active`**, the parameter default. After this change the
  field means *NMAS onboarded this device*, not *it answered a ping*, and
  onboarding reached the device before the record existed, so the claim is
  earned.
- **`status_cache` keeps its legitimate use**: deciding which devices get a
  live SSH session for neighbour discovery. Not opening a session to a device
  that is down is a correct use of liveness, and removing it too would be the
  fix overshooting into a different defect. A control pins it.

### Correcting what is already wrong

Dropping the write leaves every wrong value in place **for ever**, because
nothing will write the field again. `scripts/nmas-netbox-status-reset` corrects
them once — dry run by default, `--apply` to write:

- target is `active`, for the reason above
- **provenance governs**, exactly as removal does: only devices NMAS created
  (tagged **or** recorded). A device a human curated, or deliberately set to
  `planned` / `staged` / `decommissioning`, is **reported and left alone**
- it goes through `_nb_patch`, so it is gated on `netbox_allow_writes` and
  **recorded in the modification log** like any other write

### The source filter

`DEFAULT_CONFIG["filters"]["status"]` was `"active"` and is now `""`.

Closing the status write alone would have replaced a loud loop with a quiet
permanent one: with status frozen at whatever it was when the device was
created, a device that happened to be unreachable during its first sync is
**invisible for ever**. *If status no longer tracks liveness, filtering on it
selects for an accident of onboarding.* An operator who wants only active
devices can still set it; what changed is that nothing assumes it.

The docstring example was changed too — it showed `"status": "active"` and
would now read as the default, which is the `manifest.py` slug example again:
confident prose beside correct code.

### The sweep: what else writes an observation from an expression

Asked because a rule gets applied to things that **have names** — a 140-line
SSH scanner was deleted under *"importing observed state into the source of
truth is the wrong direction"* while three words on a call site doing the same
thing survived it.

Parsed every NetBox payload literal in `netbox_client.py` and classified each
field by how its value is produced. **Four more writes carry observed state**,
and the useful part is that the obvious discriminator is wrong.

*Observed versus intended* does not separate them: the NetBox import is
**designed** to run from golden configs, which are observations too — but
**approved** ones. The line that actually matters is:

> **does this field change without anybody deciding it?**

| field | source | verdict |
|---|---|---|
| `status` | ping cache, 5s loop | **fixed** — changed on a timer, decided by nobody |
| `comments` | `facts` + `Synced: <timestamp>` | **churns every sync by construction** |
| `local_context_data.ndm_sync` | `time.strftime(...)` | **churns every sync by construction** |
| `serial`, `custom_fields.os_version`, `local_context_data.{platform,os_version,model}` | `facts` | fine — change when the hardware or image changes, which is a fact worth recording |

### The churn is the record's own "somebody turns it off"

`comments` and `ndm_sync` both embed the time the sync ran, so **they differ on
every sync by construction** — which means the modification record logs a
change for **every device, every sync, for ever**, and `ndm_sync` sits *inside*
`local_context_data`, so that field's hash differs every sync too.

That is the same end the 113 KB would have reached, by a different road: not
volume of bytes but volume of meaningless entries. A log in which every entry
is *"the sync ran"* teaches the reader to skip it, and the next s1 goes past
unnoticed.

**Not applied** — it changes what NetBox stores. The options are to drop the
timestamp from both (the sync time is already in NetBox's own `last_updated`),
or to exclude a named set of churn fields from the record. The first is
honest and the second hides a real write, so the first is the recommendation.


## 16. The reset refused to undo its own write, and why s1 has no provenance

The first `nmas-netbox-status-reset` reported:

```
0 device(s) NMAS created with a status other than 'active'
1 device(s) SKIPPED — NMAS did not create them, so their status is somebody's decision:
    s1   offline
```

Correct by its own rule and **false about the fact**. NMAS wrote that
`offline` at 05:22, from the ping cache, and `netbox_modified.json` holds the
entry: `before {'label': 'Active', 'value': 'active'} → after 'offline'`. The
status was not somebody's decision, and the tool refused to correct a value it
had itself made — in a message asserting the opposite.

### Provenance-by-creation is the wrong test for a field-level correction

*Did NMAS create this object* and *did NMAS write this value* are different
questions. Removal needs the first, because deleting an object it did not
create is unrecoverable. A **field-level undo** needs the second — and the
second was **unanswerable** until the day before, which is why the script was
written against the wrong one.

So the reset now takes its authority from the **modification record**, and
that is strictly better than resetting to `active`: it restores *what the
field held before NMAS touched it*. `active` for s1, and `staged` for a device
somebody had deliberately staged.

`_restore_target()` walks backwards from the most recent write while each
entry's `before` is the previous entry's `after` — an unbroken run of NMAS's
own writes — and **stops where the chain breaks**, because a gap means
somebody set the value in between and theirs is the one to restore. Three
refusals rather than a default, since this script exists precisely because a
value was asserted without being known:

- a write with no recorded before-state → **refuse**, do not fall back
- the device's current status is not what NMAS last wrote → somebody has set
  it since, **theirs stands**
- no recorded write at all → *"this script only undoes writes it can prove
  NMAS made"*

### Why s1 is in no created-record — measured

Both halves of provenance, the `nmas-managed` tag and
`netbox_created_ids.json`, arrive in the **same commit**: `eac9c5e`, *NSOT
Phase 0*, **2026-09-20**. The NetBox sync itself dates from `3135efd`,
**2026-04-22**. The nine reference devices were imported by five months of an
importer that had no provenance mechanism at all, so they carry **neither**
the tag nor a record. r6 was onboarded after Phase 0 and carries both.

**Ten devices in NetBox, one of them removable.** That is the state to know
before the next teardown: a provenance-based Remove can act on r6 and is
blind to the other nine — which is *safe*, and means the mechanism has never
been proven against them and by construction never can be. Adopting them is a
deliberate act (tag plus record, for objects a human should confirm are
NMAS's) and is not something to do accidentally in passing.

### A third churn source, found while reading the log's own data

The recorded `before` was `{'label': 'Active', 'value': 'active'}` and the
`after` was `'offline'` — because NetBox renders an enum as
`{"value", "label"}` and accepts a bare string, and `_comparable` reduced a
**reference** (`{"id": N}` → `N`) while leaving an **enum** alone.

So an **unchanged** enum compared unequal, and the record logged a change that
did not happen. Reachable today: `_ensure_ip_address` PATCHes its whole
payload when only the description or VRF differs, and that payload carries
`status`. The same churn class as the sync timestamps, one layer down — in the
comparison itself rather than in a field. Fixed, keyed on the exact shape so
an arbitrary dict carrying a `value` key is left alone, with a floor that a
real enum change is still recorded.


## 17. A restore must not walk past a create — and the report is what caught it

The dry run offered two rows:

```
s1   offline → active   (NMAS wrote 'offline' over 'active')    correct
r6   active  → offline  (NMAS wrote 'active'  over 'offline')   WRONG
```

r6 is up, reachable, and was onboarded by the tool an hour earlier. Applying
that would have taken a correct value and replaced it with the absence of a
decision.

### The mechanism, measured — and it is one step from the obvious reading

It is **not** that the chain walk passes a create. It is that **the log holds
only updates**: `_nb_post` calls `record_created`, `_nb_patch` calls
`record_modified`, and nothing writes a create into the modification record.
Asserted now rather than assumed.

So r6's history is:

1. **POST** at onboarding, `status` from the ping cache — and the ping worker
   had not yet seen a device that had just booted, so `.get(ip, False)` missed
   and it was **created `offline`**. *(That path is already fixed: the call
   site's `status=` argument is gone, so creates now take the `active`
   default. r6 predates it.)*
2. **PATCH** at a later sync, once the cache had it: `offline → active`. **One
   logged entry.**

The unwind consumes that single entry and arrives at `before: offline` —
which is not a prior state at all, but NMAS's own create-time write.
**Reaching the earliest logged entry does not mean reaching the object's
origin.**

### The fix, and why it is not the first version's test returning

`_restore_target()` now reports `reached_start` — whether the unwind consumed
every logged entry — and the plan refuses when `reached_start` **and** NMAS
created the object.

The created-object record is consulted again, for **the question it actually
answers**:

| record | question | used for |
|---|---|---|
| modification log | did NMAS **write this value** | authority to correct |
| created-object record | did NMAS **create this object** | whether *"before NMAS"* names anything |

The first version used creation as *authority*, and so refused to undo NMAS's
own write on s1. This uses it as an *existence* test, and only where the
unwind ran out of log. **A gap in the chain means a human's value, which is
meaningful however the object came to exist** — so a device NMAS created whose
status a human later set is still restorable. That scoping is the whole
difference, and both directions are controlled: removing the stop reproduces
the r6 row, and applying it regardless of `reached_start` makes s1 unfixable
again.

Tag **or** record, because the tag is injected in `_nb_post` only — so a
tagged object was created by NMAS even where a deleted list took its record.

### What caught it

The report named both operands: *"NMAS wrote 'active' over 'offline'"*. The
wrong row was readable at a glance, by the operator, before anything was
written.

The previous version of this same report said `0 device(s) to correct, 1
skipped` — a count with no operands — and it would have been applied without
anybody knowing. **The naming-both-operands rule paid for itself twice in one
evening**: first when `skipped_drifted` reported neither hash and cost three
wrong hypotheses, and now when a restore plan printed what it was replacing
and stopped a bad write before it happened.

The difference between the two reports is not detail. It is that one makes a
claim a reader can check and the other asks to be trusted.


## 18. Verifying the noise fix — and why "no entries" cannot be the check

s1 is restored: `06:07:55  s1  before 'offline' → after 'active'`, all ten
active, a re-run reports nothing to restore and r6 skipped with its reason.
**The correction is itself in the log**, which is the property that makes the
record worth having.

### A fourth churn source, found by the verification rather than by the sync

The claim to verify was *"an unchanged device now produces no entry at all"*.
Written as a test over the payload `_upsert_device` **actually sends**, it
failed immediately:

```
device_role: {'before': '<unknown>', 'after': 2}
```

`role` and `device_role` are **one field under two names** — NetBox 3.x called
it `device_role`, 4.x calls it `role` — and the payload sends both so either
server accepts it. A server echoes only its own, so the other is **absent from
the response**, which the record correctly reports as `before: <unknown>`.

An entry for every device on every sync, for ever, and the worst-looking of
the four: `<unknown>` is the shape of a **failed read**, not of a no-op. On an
update the sync now sends only the alias the server uses; creates still send
both, where compatibility matters and nothing is logged anyway.

**The first version of that test bypassed the filter it existed to
exercise** — it called `changed_fields()` on a hand-built payload, testing a
payload no code sends. It drives `_upsert_device` now and asserts what reaches
`_nb_patch`. And its fixture was wrong too: a hand-written
`local_context_data` is thinner than what the sync writes, so an unchanged
device looked changed. It is built with the real producer.

### "No entries" is exactly what a broken recorder produces

Four sources of noise removed, and **silence is now the expected result** —
which is also precisely what a recorder that has stopped working looks like. A
verification that only checks for an absence of entries cannot tell those
apart. *The vacuous pass, inside the check built to confirm the fix for
noise.*

So the verification has two halves, and the second is load-bearing:

```bash
# 1. the noise is gone
python3 scripts/nmas-netbox-modified        # note the entry count
#    run a sync
python3 scripts/nmas-netbox-modified        # the count must not have moved

# 2. THE RECORDER STILL WORKS — change something real first
#    e.g. edit a device's description in NetBox, then sync
python3 scripts/nmas-netbox-modified        # that change MUST appear
```

**Predicted in advance so it is not misread**: `local_context_data` carries
the sanitised running config, so a device whose config genuinely moved still
logs — summarised to size and hash. On r1–r5 that includes the regenerated
self-signed certificates already documented as a standing difference. That is
a real change being reported, not the fix having failed.


## 19. A fifth churn source: an unordered collection compared as an ordered one

```
2026-09-25T06:15:43Z  dcim/devices/6 r2
    tags: [4, 2, 1] → [1, 2, 4]
```

The same three tags in a different order — logged as a change on every sync,
for every device with more than one tag, and reading as though the tags had
been rewritten.

### Two defects, and only fixing the comparison would have hidden the worse one

`_comparable` compared lists **positionally**, so a reordered m2m reference
read as a different value. That is the reported symptom.

The cause is in the caller:

```python
merged = list(set(current_tags + tag_ids))
device = _nb_patch(..., {"tags": merged})
```

`list(set(...))` hands back an arbitrary order, and **the PATCH fired
unconditionally** whenever the device had any protocol tag — so this was a
*guaranteed no-op write on every sync, for ever*, with NetBox bumping
`last_updated` for nothing.

Comparing unordered alone would have made the **entry** disappear while the
pointless write carried on — the log quietly stopping covering a write that
happens every time, which is the checker-exemption shape again. So: `sorted`
makes the value stable, and `if set(merged) != set(current_tags)` means the
write does not happen at all.

### Named fields, never "every list"

`UNORDERED_LIST_FIELDS = {"tags", "tagged_vlans", "object_types"}` — each a
**many-to-many reference**, which NetBox returns in whatever order it pleases.

The default stays **ordered**, because order carries meaning in plenty of
places — an ACL, a route-map, a prefix-list. This project already learned that
once, for config sections: `section_is_unordered()` is an allowlist and
*order-significant anywhere wins*. A control treating every list as a set
fails, which is what keeps this from degrading into *"lists never differ"*.

Cable `a_terminations`/`b_terminations` are deliberately absent: POST-only
today, and a list of dicts needs a stable identity to sort on — a different
problem from this one.

### The count, and what it says about the record

Five churn sources, all found within a day of the record existing, none of
them visible before it:

| # | source | why it churned |
|---|---|---|
| 1 | `comments` | embedded the sync's own timestamp |
| 2 | `local_context_data.ndm_sync` | same timestamp, one level down |
| 3 | enum vs reference in `_comparable` | `{"value","label"}` never equalled `"active"` |
| 4 | `role` / `device_role` | one field under two names; the server echoes one |
| 5 | `tags` | a set compared as a sequence, plus an unconditional write |

**Every one of them was a write NMAS had been making for months**, and the
only reason they are visible now is that something finally recorded what it
wrote. A record that nobody can bear to read is worth nothing — which is why
each of these mattered enough to fix rather than filter.


## 20. A sixth: a guard that could never be satisfied

```
06:21:41  extras/config-templates/1  template_code: 519 B → 521 B (sha e96268e9b1e2 → 57cda3e1ac6b)
06:24:19  extras/config-templates/1  template_code: 519 B → 521 B (sha e96268e9b1e2 → 57cda3e1ac6b)
```

**Identical before *and* after, twice.** The log's own repetition is what
proved this was representational rather than a content change — a content
change would have moved one of the four numbers.

### The two bytes, measured

Not guessed. The sizes are JSON-serialised, which is the whole explanation:

```
raw length                508
json-serialised           521      <- what NMAS sends
one trailing \n removed   519      <- what NetBox stores and returns
```

**NetBox strips a trailing newline from `template_code` on write**, and one
newline is *two* characters once JSON-escaped. Exactly the reported delta,
arrived at by arithmetic.

### The guard was there, and had never once been true

`_ensure_config_template` already guards its write:

```python
if existing.get("template_code") != _NDM_TEMPLATE_CODE:
```

It compares what NetBox stores against a constant NetBox will never store, so
it was **permanently true** and the template has been rewritten on every sync
since it was introduced. *A guard that can never be satisfied is worse than no
guard, because it makes the write look considered.*

Same two halves as the tags fix, and the same ordering: the comparison is one
of them and the unnecessary write is the other. Here one change closes both —
the constant is defined as **what NetBox will actually store**, so what is sent
equals what comes back and the existing guard starts working for the first
time.

### What was deliberately not done

`.strip()` on both sides of the comparison would also have silenced it — and
would paper over **any other** normalisation NetBox applies, which is precisely
the class of thing the record exists to reveal. It would also stop a genuine
template edit ever being deployed if it differed only in whitespace.

Fix the discrepancy that was measured; let the record surface the next one.
That is how this one was found.

### Six sources, and the pattern across them

| # | source | shape |
|---|---|---|
| 1 | `comments` timestamp | a field that changes because the sync ran |
| 2 | `ndm_sync` | the same, one level down |
| 3 | enum vs reference | two representations of one value |
| 4 | `role`/`device_role` | one field under two names |
| 5 | `tags` | a set compared as a sequence, and an unconditional write |
| 6 | `template_code` | a value that cannot round-trip, and a guard that therefore never held |

Three of the six are **two representations of the same fact** compared as if
they were two facts. That is worth naming as the dominant shape: the record
did not find six unrelated bugs, it found one kind of mistake six times, and
it could only find them by writing down what was actually sent.


## 21. The recorder cannot fail silently — and C1 was a misreading

### C1 first, because it decides what any measurement is worth

*"`nmas-deploy` reports already at `da4d479` while `32329bf` exists on
origin"* — measured:

```
$ git merge-base --is-ancestor 32329bf da4d479  →  YES
```

`32329bf` is an **ancestor** of `da4d479`. The tip already contains it, so
*"already at `da4d479`"* is **correct** and the host has every fix including
the template round-trip. The deploy tool was right.

The first report — *"already at `cfbe7fe`"* while origin was ahead, moved only
by an explicit fetch — is not explained by that and may well be real. It needs
one measurement rather than a rewrite: `git fetch && git rev-parse HEAD
origin/main` either side of a run.

**The shape is worth keeping.** C1 had been recorded as a finding an hour
earlier, and the next confusing output was attributed to it — but that output
was correct behaviour. *A pattern that has been right four times is exactly the
one to distrust on the fifth.* A register makes a finding easier to find, and
therefore easier to reach for.

### The recorder: two defects in its own write path

Whatever stopped the 06:34 entry, the recorder could not have told anybody, and
that is fixed independently of the cause.

**A failed write was swallowed.** `_write_json_atomic` catches `OSError`, logs
at ERROR and returns `False`; `record_modified` **ignored the return**. So a
record that could not be written reported nothing at all, while
`nmas-netbox-modified` went on printing `0 modifications` — which is how *"the
noise is gone"* and *"the recorder stopped"* became indistinguishable. Failures
are counted now and printed **beside every count**, with the count named as a
**floor, not a total**.

In memory, like `redact.health()`, and for the same reason: *a record that
cannot be written cannot write down that it could not be written.* Lost on a
restart, which is stated rather than hidden.

**And an unreadable record would have been erased.** `_load_modified()` turns
an unreadable file into `{}`; appending one entry to that and writing it back
replaces the entire history. **The settings-file erasure verbatim**, one store
over — a partial read returned `{}` and the next write persisted it. `absent`
is fine and still writes; `unreadable` now **refuses, counts, and leaves the
damaged file alone**.

### The one measurement that settles the 06:34 silence

Two states produce *"comments read canonical, no entry"*, and they are
opposite:

1. a sync ran, overwrote the edit, and the record failed to say so
2. **no sync ran after the edit** — in which case the edit never saved, and
   there is correctly nothing to record

NetBox's own `last_updated` on r1 separates them, and nothing else has to be
believed:

```bash
curl -s -H "Authorization: Token $TOKEN" \
  "$NETBOX/api/dcim/devices/?name=r1" | python3 -c \
  "import json,sys; d=json.load(sys.stdin)['results'][0]; \
   print(d['last_updated'], '|', d['comments'][:60])"
```

`last_updated` **after** the edit means a write happened and the recorder was
silent — finding (1), and `health()` will now say whether it failed or simply
saw nothing to record. `last_updated` **before** the edit means no write
happened, the recorder was correct, and what failed was the edit.

Ask the cheapest question that halves the space, rather than the most likely
explanation. It has been wrong three times running in this project by the
other route.


## 22. The comparison is not eating it — measured, and the fix could not have said so

`last_updated 2026-09-25T06:34:39Z`, 49 seconds after the patch, comments back
to canonical. A write happened and the recorder said nothing.

### The trailing-whitespace hypothesis is refuted at the code level

It was the right hypothesis to raise — *a fix for noise that suppresses signal*
would be the worst of the six, and three of the six **are** normalisations. So
it was tested rather than argued:

```
changed_fields({"comments": canon + " TEST"}, {"comments": canon})
  -> {'comments': {'before': '… 10.255.1.11 TEST', 'after': '… 10.255.1.11'}}
```

`_comparable` strips nothing from a string, `comments` is not in
`UNORDERED_LIST_FIELDS`, and `record_value` returns both verbatim. Then driven
through the **whole** path — `_upsert_device` → `_nb_patch` → the record, with
the patched comments as the stored value and a spy session:

```
comments sent  : 'Platform: IOS  |  Version: 17.6  |  Mgmt IP: 10.255.1.11'
entries recorded: 1   dcim/devices/6  ['comments', 'local_context_data']
```

**The repository's code records it.** So the deployed behaviour and the
repository's behaviour differ, and the remaining causes are all about *which
code ran and whether it could write*, not about what it compared.

### The gap in the fix, which is mine

`health()` counts **in memory**, and the recorder runs **inside the Flask
app** — while `nmas-netbox-modified` is a different process. So the health
line the CLI prints is about the CLI, and would have read `0 writes failed`
however badly the app was failing.

*The reassuring zero, one level up*: the check built to stop **silence**
meaning two things was itself silent about whose silence it reported. It now
says so in its own output and names the channel that does cross processes —
the app log, which both `_write_json_atomic` and `record_modified` write at
ERROR.

### The three discriminators, in order, cheapest first

**1. Is the app running the deployed code at all?** A long-running Flask
process holds its modules in memory; updating files changes nothing until it
restarts.

```bash
ps -o lstart= -p "$(pgrep -f 'python.*app\.py' | head -1)"
```

A start time **before** the deploy ends the investigation: the churn fixes,
the comparison and the recorder were all the old ones, and nothing measured
since applies to the code in the repository.

**2. Did the write fail?** This is the one `health()` was for, and the log is
where it crosses:

```bash
journalctl -u nmas --since today | grep netbox_guard
```

`could not persist` means the file write failed — permissions are the
candidate, since `--sanitise` and `--apply` were run from a shell and
`_write_json_atomic` creates `0600` owned by whoever runs it. `NOT recording
a modification` means the existing record was unreadable, which after
`67e3c58` refuses rather than erasing.

**3. Only then, the comparison.** With both above clean, patch `comments`
again and sync with the fixed recorder deployed. Silence at that point, on
code proven to record the same change in the harness, would mean the deployed
path differs from the tested one — and the next question is which.

The ordering matters because the expensive hypothesis is third. Two rounds
have now gone to *a pattern that has been right before*, and both times the
cheap question was available from the first report.
