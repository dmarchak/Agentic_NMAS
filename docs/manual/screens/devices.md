# Devices

Every device in the network, searchable and filterable.

## The list {#the-list}

Each row: the device's status (answering or not, from the reachability reader), its address
and platform, whether it was at its committed intent when it was last MEASURED and by
what, and when that was. Hover the time to see when its golden last changed. Onboardings
still pending are rows too, and open their own page.

## Drained {#drained}

**Switched off for now:** in a network managed in band, the manager's own polling crosses data
interfaces at about the rate customer traffic does, so interface counters cannot tell a
drained device from a quiet one. No badge is drawn and no alert is held back until Drained is
measured from customer traffic by address. What follows is how it worked while it was on.

A **Drained** badge beside a device's name (and in its page's header) is MEASURED, never set
by hand: every interface that is up, not a loopback, not in a VRF, and not the device's
management path (the interface its golden gives the management address) carried less than
0.5 unicast packets a second, in and out, over the last 3 minutes, read from the interface
counters Prometheus already scrapes. Its words name each interface, its rates now and since
when it has been quiet. It goes when traffic rises again. A device with no golden, or whose
management address is on no interface in its golden (a loopback), is not judged, so it is
never drawn drained. Needs attention lists a Grafana alert on drained devices only under What
was checked instead of raising it as a row.

A measurement is any save that read the device and compared it with its golden: a capture,
a deploy's or restore's read after the push, and a Save All that found it unchanged (which
records its decision in a commit of its own, naming every device it read). The intent state
is the newest measurement's, read from that commit, never by reading the device now. A
capture or Save All (see [Capture and Save All](capture)) brings it up to date. The device
page's Overview compares the golden with intent live and says when it was last measured.

A Save All that changed some goldens before 2026-10-02 named only those devices, so an
unchanged device's read in it is not recoverable; its last measurement reads as the save
before.

## Startup {#startup}

What the hourly startup check last read of each device: **accounts saved** when every
`username` line of the running configuration was in startup, **accounts not saved** when one
was missing (a reload would boot without it), **unknown** when the check could not read the
device, and **not checked** when the check has not recorded it. The check compares the
accounts only, so the column never says the whole startup matches running; hover a badge for
what the check found. An unreadable check record is said above the list.

## Selecting devices {#selection}

Tick devices and the bar above the list names them, with **Actions** and **Clear selection**.
The Actions menu:

- **Plan a deploy for the ticked devices…** opens Devices › Plan a deploy: each device's whole
  committed intent planned at once, the devices in a rollout order you can change (Earlier,
  Later, Leave out), each device's exact program and what it holds back, then one confirm. The
  batch runs as a job, one device at a time in that order, each verified and rolled back alone,
  and stops after repeated failures. Merge-only: lines a device holds that its intent lacks
  stay; Remove lines (Mode B) is on each device's page. See [Deploy](deploy).
- **Save (N)…** opens Devices › Save for the ticked devices: each saves its running
  configuration to startup, is read back, and is recorded as golden, one commit for the batch.
  See [Save to startup and as golden](save).
- **Save every device of the network…** opens the same Save for every device in the inventory;
  it is Save All: it asks for a baseline, earned when every device was saved and recorded at
  its committed intent, and the result says which, or why not.

The rows ticked are kept when the list redraws.

## Add device {#add-device}

**Add device…** opens a card above the list for a NEW device in this network (the top bar's
network picker chooses which). Fill in its name, platform and role, how it gets its address
(static, a DHCP reservation, or ZTP, where the tool reserves the address and serves the
configuration), the address, mask and MAC that source needs, the interface the address goes
on, a gateway when this host is not on the device's subnet, and the DNS domain. A platform not
yet onboardable is listed and disabled, with its reason.

**Review the plan** creates nothing. It shows every reason the device cannot be onboarded at
once, and otherwise the startup configuration it will boot (with a placeholder for the
one-time password, which is generated at Create and never sent to the browser), what Create
will make, and what it does not do. **Create** builds the plan again holding the device's
name, and refuses, naming each value that moved, if it is not the plan you reviewed; it needs
a verified person. The result says the device is PENDING (created, never reached), and
**Open its page** goes to its pending page, where Verify, the bootstrap configuration and
Abandon are. See [Onboard a device](onboard).

## Adopt a device {#adopt}

**Adopt a device…** opens a card for a device the tool did NOT build: one already running,
with a working login somebody gives. Fill in its name, management address, platform and role,
and that login. **Read it and preview** reads the device over the login and sends nothing: it
shows every check by name (each reason it cannot be adopted, all at once), the lines it will
send (masked), what a save makes permanent, and what it does not do. The password is never
drawn back, so **Adopt** asks for it again, with why; it needs a verified person, reads the
device again and stops, sending nothing, if it moved since the preview. The card follows the
run's steps and then draws each one's outcome. An adopted device's result names what finishes
it, in order: **Seed its intent…** (the fidelity and one commit as its intent), then **Export
the break-glass record…**. See [Adopt a device](adopt).

## A pending device's page {#pending}

A device created and not yet reached has no tabs: its page shows its onboarding state, its
address and how it gets it, and three actions, each answered in place:

- **Verify…** reaches the device and reads it (sending nothing), then shows what Verify will
  send; **Verify** confirms that preview. See [Onboard a device](onboard#phase-two-verify).
- **Get the bootstrap config…** shows the configuration the device boots with, its one-time
  password in the clear. It is a reveal: it needs a verified person and is recorded.
- **Abandon…** shows what abandoning would remove, step by step, removing nothing; **Abandon**
  confirms it, and is refused, removing nothing, if what it would remove moved since you
  looked.
