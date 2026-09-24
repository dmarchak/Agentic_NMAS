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
- [ ] **the lease is reserved, not dynamic** — or the device's address changes
      under the tool at the next renewal, which is a worse failure than not
      having DHCP
- [ ] teardown: census `--compare` clean, exit 0

### Explicitly out of scope

* **Re-addressing a managed device.** A separate capability, wanted by
  nothing today. If it is ever built, the design problem to solve first is the
  one in §2: a repair path that does not travel over the address being
  changed.
* **The relay** — phase 3, behind a switch. Phase 2 is L2-adjacent to the pool
  on purpose, so a failure means *"the device did not fetch"* rather than
  *"something between them did not forward"*.

## 4. What this leaves r6 as

The working branch site, untouched: committed intent, a golden, a `/32` the
fleet learns as extern 2 metric 20 from `10.255.1.23`, and a startup file that
survives a reboot. **Its acceptance stays a live regression check** — whatever
phase 2 does elsewhere, `r1` must still learn `10.255.1.16` in that exact
form.
