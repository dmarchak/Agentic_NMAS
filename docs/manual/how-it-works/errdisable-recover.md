# Recover an err-disabled interface

A switch err-disables an access port when one of its protections trips: **BPDU guard** (a
switch or a bridge was plugged into a port meant for one host) or **port security** (a second
MAC address appeared on a port that allows only the secure one). The port stays down until it
is recovered, and the host on it has no network. Mercury names the problem from the switch's
own evidence ("edge-sw1 Gi1/0 err-disabled by BPDU guard: pc-12 is offline", a warning: one
host down is not a network outage), confirms it on the device, and recovers the port only once
its cause has gone. It never races the switch's own `errdisable recovery`.

The recovery is a **command plan** that ships with Mercury, not an operation of its own: a
reviewed document naming the lines it sends (`interface <port>`, `shutdown`, `no shutdown`),
its typed parameters, the reads that must hold before anything is sent, and the reads that
verify it. It runs on the same engine every deploy runs on: the same hold on the device, the
same gate on dangerous lines, the same reads before and after, the same rollback and the same
record.

![Recover an err-disabled interface, a built-in command plan run on the deploy pipeline's engine: its parameters are validated against Mercury's model (the port in committed intent, an access port, never the management path) and its lines held to Mercury's rule for raw lines; you approve by the plan's hash; holding the device, the running configuration is read, then each precondition through the read engine (the port err-disabled by the cause now, no errdisable recovery for the cause, the cause cleared), else nothing is sent; then interface, shutdown and no shutdown, never saved; verify reads the port every 3 seconds until connected, up to 30, and no new err-disable 10 seconds later, then the running configuration must equal the one before, line for line; anything else is rolled back by the pipeline; the receipt and the run are recorded and the engineer told the offending MAC, the port, the time and the cause.](diagrams/errdisable-recover.svg)

## How the problem is named {#problem}

The incident opens from the switch's own alerts (Grafana's "Critical syslog received" and
"Interface down"). Mercury reads the switch's lines from when the incident opened: the
`%PM-4-ERR_DISABLE` line names the port and the cause (`bpduguard` or `psecure-violation`), a
`%SPANTREE-2-BLOCK_BPDUGUARD` line says a BPDU arrived, and a
`%PORT_SECURITY-2-PSECURE_VIOLATION` line names the MAC that tripped it. The Interface down
alert's port must be the same port, or nothing is named, and the incident page says why. The
host it serves and its VLAN come from the port's description and access VLAN in intent; the
port's role (access or trunk) from its switchport mode. Then the switch is read once, `show
interfaces status err-disabled`, and that read is drawn on the incident page as its evidence:
which port, which cause, and when it was read. If the switch disagrees with the evidence,
Mercury takes no action and says so. An incident opened before Mercury knew this problem is
named the same way, from its own evidence, without the fault being injected again.

On Needs attention the incident is one row in the same words as Troubleshooting › Incidents
and its page, and its two alerts are folded under it as its evidence.

## Before you approve {#plan}

The recovery is offered on the incident's page, as a step of the incident's plan. Before it is
drawn, Mercury checks it, asking no device:

- **The parameters against Mercury's model.** The device is one of the network's; the port is
  in its committed intent, is an access port there, and is not on the path Mercury manages the
  device through (the interface holding its management address, IPv4 or IPv6, or addressed by
  DHCP, or an access port in that address's VLAN). The cause is `bpduguard` or
  `psecure-violation`. Each value Mercury sends is the validated one (the port by its full
  name), never text a person or the AI typed.
- **Mercury's rule for raw lines.** Every line is a shape Mercury has measured on the device's
  platform; reload, erase, delete, boot, accounts, AAA, crypto, a vty line, a save, and an
  object not named by a parameter are refused whoever proposed them. These three shapes were
  sent by this recovery before it became a plan, and its first run records their measurement.
- **The golden.** A golden holding `errdisable recovery cause <cause>` (or `all`) refuses the
  plan: the switch recovers the port by itself, and Mercury does not race it.

What its hash binds is drawn before Approve: the plan and its version, the network, the
device, the port and the cause, the lines with the reason for the dangerous one, each
precondition and each verify read with its wait, and the rule that the configuration after
equals the one before. Only a verified person approves it.

## The run, step by step

1. **Check the hash** (`approve`). The plan is checked again as above; one that moved since you
   approved it is refused, naming both hashes, and nothing is sent.
2. **Hold the device** (`hold`) for the whole run: one operation per device. Every line
   Mercury's session sends while it holds the device is Mercury's own on the device's history.
3. **Read before** (`read_before`): the running configuration, read before anything is sent.
   If it cannot be read, nothing is sent: whether the plan left the device as it was could not
   be checked.
4. **Check the preconditions** (`preconditions`), each read again through the read engine,
   holding the device: the port is listed in `show interfaces status err-disabled` with the
   cause; the running configuration's `errdisable recovery` lines hold none for the cause; the
   cause has cleared (for BPDU guard, no BPDU guard line for the port in the switch's lines
   since the err-disable; for port security, the violating MAC from the incident on neither
   `show port-security address` nor `show mac address-table interface <port>`). Any that does
   not hold, or cannot be read, stops the run with nothing sent. Not cleared: "Port stays
   down: the device that tripped it (MAC aa:bb:…) is still connected", and the engineer is
   notified.
5. **Send** (`send`): `interface <port>`, `shutdown`, `no shutdown` in config mode, never saved.
6. **Verify** (`verify`). The deploy's own verify first: the port coming up is the plan's
   intended effect, and any other interface going down is not. Then the plan's reads: `show
   interfaces status` every 3 seconds until the port reads connected, for up to 30 seconds,
   then the err-disabled view once more after 10 seconds (a port err-disabled again means its
   cause is still there). Then **net zero**: the running configuration is read again, holding
   the device, and must equal the one read before, line for line (leaving out the lines the
   device rewrites by itself: the last-change and NVRAM comments, `ntp clock-period`). Any
   difference fails the run, each line named.
7. **Roll back** (`rollback`) when it did not verify: the deploy's own rollback, from the
   configuration read before, read back afterwards and saying what it achieved.
8. **Record** (`record`): a receipt on the device's History ("Ran reviewed commands"), the run's
   record with each step, each precondition and verify read and the net-zero result, and a
   message to the teams told about self-healing naming the offending MAC (when port security
   logged one), the port, the time of the err-disable and the cause.

## What it does not do {#not}

- It does not clear the cause: unplug the bridge, or remove the foreign device, first.
- It never changes or saves the configuration, and never adds a secure MAC: a plan that would
  leave any line changed is rolled back and refused. A lasting change goes through intent.
- It never acts on a port the switch did not confirm err-disabled, nor where the switch's own
  `errdisable recovery` covers the cause.
