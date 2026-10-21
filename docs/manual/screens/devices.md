# Devices

Every device in the network, searchable and filterable: a box searches by name or address,
and two menus filter by intent state (each state with its count) and by platform. Under a
search or a filter, the list says "Showing N of M".

## The list {#the-list}

Each row: the device's status (answering or not, from the reachability reader), its address
and platform, whether it was at its committed intent when it was last MEASURED and by
what, and when that was. Hover the time to see when its golden last changed. Onboardings
still pending are rows too, and open their own page. A pending row says where its onboarding
has got to as its page does, from the onboarding-progress reader's last read: "answering:
ready to Verify", a ZTP device's stage ("ZTP: fetched its config; not answering yet"), or
"pending: not read yet", the stage's detail on hover and "read <age>" after it; a ZTP device's
address says ZTP. The list draws itself again when that reader sees a pending device move.

## Drained {#drained}

**Switched off for now:** in a network managed in band, the manager's own polling crosses data
interfaces at about the rate customer traffic does, so interface counters cannot tell a
drained device from a quiet one. No badge is drawn and no alert is held back until Drained is
measured from customer traffic by address. What follows is how it worked while it was on.

A **Drained** badge beside a device's name (and in its page's header) is MEASURED, never set
by hand: every interface that is up, not a loopback, not in a VRF, and not the device's
management path (the interface its golden gives the management address) carried less than
10 unicast packets a second, in and out, for 3 minutes (a floor set above the manager's own
polling), read from the interface counters Prometheus already scrapes. Its words name each interface, its rates now and since
when it has been quiet. It goes when traffic rises again. A device with no golden, or whose
management address is on no interface in its golden (a loopback), is not judged, so it is
never drawn drained. Needs attention lists a Grafana alert on drained devices only under What
was checked instead of raising it as a row.

A measurement is any save that read the device and compared it with its golden: a capture,
a deploy's or restore's read after the push, and a Save All that found it unchanged (which
records its decision in a commit of its own, naming every device it read). The intent state
is the newest measurement's, read from that commit, never by reading the device now, and it
is drawn only while nothing that measurement was judged against has moved since. When the
device's committed intent, the network's monitoring profile or the template library has a
commit after it, the row says **intent changed since measured** instead, and its hover names
what changed, when, and what the measurement had read: the recorded "departs" or "at intent"
may no longer be true. A capture or Save All (see [Capture and Save All](capture)) brings it
up to date. The device page's Overview shows the same state, from the same reading, beside
its Intent check, which compares the golden with intent now.

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

The box in the table's head, **Select the N shown**, ticks every row the list shows under the
current search and filters (a device pending onboarding has no tick, so it is never one of
them), and unticks them again; with only some rows ticked it shows a dash. The list draws
every device that matches, so with every row shown ticked the selection is **all matching**,
and the bar says so: "All 412 matching selected" under a search or filter, "All 900 selected"
without one. An action then receives the search and filters, never the names, and works out
the devices itself from them, the same way the list did; its plan or preview names how many
and each one, so a device that came to match since the list was drawn is named there before
anything is done. Untick one row and the selection is the ticked names again.

The Actions menu:

- **Plan a deploy for the ticked devices…** opens Devices › Plan a deploy: each device's whole
  committed intent planned at once, the devices in a rollout order you can change, each
  device's exact program and what it holds back, then one confirm. Drag a device by its grip,
  or use Earlier and Later (the keyboard's and touch's way): the order changes on the page at
  once and plans nothing, since no device's program depends on its place, and a device let go
  outside the list stays where it was. Leave out plans the batch again without that device.
  The confirm sends the order the list shows, and is refused unless it names exactly the
  devices confirmed. The batch runs as a job, one device at a time in that order, each
  verified and rolled back alone, and stops after repeated failures. While it runs, the
  preview says so and its controls do nothing; once it has ended, the preview says that. Merge-only: lines a device holds that its intent lacks
  stay; Remove lines (Mode B) is on each device's page. See [Deploy](deploy).
- **Save (<count>)…** opens Devices › Save for the ticked devices: each saves its running
  configuration to startup, is read back, and is recorded as golden, one commit for the batch.
  See [Save to startup and as golden](save).
- **Change a setting on (<count>)…** opens a page for one change to the ticked devices' committed
  intent: each setting's path, the value it holds now and the value it becomes. Its preview
  refuses, by name, any device holding something else, groups the rest by what changes, and
  commits once; nothing is sent until you deploy. See [Edit intent in bulk](bulk-intent).
- **Save every device of <network> (<count>)…** opens the same Save for every device in the inventory;
  it is Save All: it asks for a baseline, earned when every device was saved and recorded at
  its committed intent, and the result says which, or why not.
- **Save the devices of <network> with no golden…** opens the same Save for every device of
  the inventory with no committed golden, decided from the network's repository; the plan
  names each device it left out, and says so when none is left to save. See
  [the devices with no golden](save#no-golden).

The rows ticked are kept when the list redraws.

## Add device {#add-device}

**Add device…** opens a card above the list for a NEW device in this network (the top bar's
network picker chooses which). Fill in its name, platform and role, how it gets its address
(static, a DHCP reservation, or ZTP, where the tool reserves the address and serves the
configuration), the address, mask and MAC that source needs, the interface the address goes
on, a gateway when this host is not on the device's subnet (behind a relay, the relay's own
address), the **Route option (3)**, the **Platform management port**
(optional: a separate port the platform manages itself on, apart from that address), and the
DNS domain. A platform not yet onboardable would be listed and disabled, with its reason; no
platform is held back today.

**Route option (3)** sits under Gateway and is drawn only while Address from is ZTP. It offers
**None (D4)**, the default, which sends the device no route option, and **The relay's own
address**, for a device behind a DHCP relay whose AutoInstall needs a route to fetch its
configuration from off its subnet; it is never a DNS server. Chosen for a device on a subnet this
host is on, the review refuses it. The review says which was chosen ("offering option 3
(routers) …" or "with no option 3"), and the reservation and its record keep it. See [ZTP behind
a relay](onboard#ztp-behind-a-relay).

**Discovered** opens the devices asking for an address on the ZTP segment that the tool does
not know, each with **Pick…**, which opens this card with the MAC it asked with: see
[Onboard devices: Discovered](onboard-discovered).

**Review the plan** creates nothing. It shows every reason the device cannot be onboarded at
once, and otherwise the startup configuration it will boot (with a placeholder for the
one-time password, which is generated at Create and never sent to the browser), what Create
will make, and what it does not do; **Change the fields** goes back to the form. **Create
<device>** builds the plan again holding the device's name, and refuses, naming each value
that moved, if it is not the plan you reviewed; it needs a verified person. The result says
the device is PENDING (created, never reached), and **Open <device>'s page** goes to its
pending page, where Verify, the bootstrap configuration and Abandon are; **Add another**
opens an empty form. See [Onboard a device](onboard).

## Adopt a device {#adopt}

**Adopt a device…** opens a card for a device the tool did NOT build: one already running,
with a working login somebody gives. Fill in its name, management address, platform and role,
and that login. Adopting adds the tool's own account, and the tool signs in with that from
then on; the login you gave is left as it is unless you turn on **store it as a hash (same
password)**. **Read it and preview** reads the device over the login and sends nothing: it
shows every check by name (each reason it cannot be adopted, all at once), the lines it will
send (masked), what a save makes permanent, and what it does not do. The password is never
drawn back, so **Adopt** asks for it again, with why; it needs a verified person, reads the
device again and stops, sending nothing, if it moved since the preview. The card follows the
run's steps and then draws each one's outcome. A run that stops can be run again from the
start: it resumes where it stopped, proving the account it added rather than adding it twice. An adopted device's result names what finishes
it, in order: **Seed <device>'s intent…** (the fidelity and one commit as its intent), then
**Export the break-glass record…**. See [Adopt a device](adopt).

## A pending device's page {#pending}

A device created and not yet reached has no tabs: its page shows its onboarding state, its
address and how it gets it, and three actions, each answered in place.

**<device> onboarding progress**, with a ZTP, DHCP or static badge, says when to press Verify.
Its five steps (identity, first-boot config, confirmed, waiting for it, arrival) are on the one
stepper, and the time on Waiting for it counts from the device's Create. The card draws itself
again whenever Mercury's onboarding-progress reader sees something move (it reads every 10
seconds: a ZTP device's stage, and whether the device answers), and when anyone creates,
verifies or abandons an onboarding; nothing on the page polls. Once a ZTP device has fetched
its configuration (a static or DHCP device at once), the reader probes its address the way the
online dot does, ICMP and then a TCP connection to port 22, sending nothing and trying no
login: **Answering: ready to Verify** says it accepted, with which probe and when; **Not
answering yet** says it did not. For ZTP the card states the stop rule, "no fetch 15 minutes
after boot: stop", and marks it in amber once 15 minutes have passed since the Create with no
fetch of its own (the tool cannot see the boot, only the Create before it). The wait is also
listed in the top bar's In progress chip ([What is running now](getting-started#in-progress)),
until Verify or Abandon ends it.

Its last Verify or Abandon is drawn beside its facts, when there is one of its own: a run of
the same name before this device's Create (a retired device's Verify, an earlier onboarding's
Abandon) is that device's, never this one's, and stays in History.

- **Verify…** reaches the device and reads it (sending nothing), then shows what Verify will
  send; **Verify** confirms that preview. See [Onboard a device](onboard#phase-two-verify).
- **Get the bootstrap config…** shows the configuration the device boots with, its one-time
  password in the clear. It is a reveal: it needs a verified person and is recorded.
- **Abandon…** shows what abandoning would remove, step by step, removing nothing; **Abandon**
  confirms it, and is refused, removing nothing, if what it would remove moved since you
  looked.
