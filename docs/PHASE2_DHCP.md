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
