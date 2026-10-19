# NetBox

Importing each network into NetBox, and removing what {{product}} put there: the sidebar's
**NetBox**. Nothing on this page reaches a device.

## What it is for {#what-it-is-for}

- **Import** builds NetBox's records from each device's committed golden. It previews every
  object it would create or change, and confirming is one-shot: it is refused if NetBox
  changed since the preview.
- **Remove** deletes only what {{product}} created (tagged AND in {{product}}'s own record), and names
  everything a deletion would take with it. **Stop tracking** instead deletes nothing: {{product}}
  forgets what it created, and NetBox keeps it.
- **Writes are off unless switched on.** A confirm here can turn them on, with your permission,
  and they come on only once its token and plan both pass; they are turned off on
  Settings › Installation's NetBox card. Every write records who and on what basis.

## Connection {#connection}

Whether NetBox answers (the integrations reader's last read, every minute) and whether writes are
on for every network. If NetBox is not configured, its address and token are set on
Settings › Installation › Connections, and nothing here runs until they are.

## Networks {#networks}

Every network, with its devices as the import reads them (its own list's, or, for a network
whose inventory is NetBox, NetBox's, marked "from NetBox"), its last import's result (complete,
PARTIAL, FAILED or nothing to do, never green over a partial; "never imported" when there is
none) and how many removals are recorded for it. The count opens the newest 20, each summarised
as it was drawn at its apply, with when and by whom; "record unreadable" says the removal record
could not be read.

- **Import into NetBox…** starts a dry run of the real import against the real NetBox, writing
  nothing. From your press until its card draws, the button says **Starting the dry run…** and
  cannot be pressed again. It is not offered while NetBox is not configured, or for a network
  with no devices to import (the button says which). It can take about a minute, so it runs as
  a job: its card, below
  the table, says what it is doing, and fills in with the preview when it is ready (every object to create or
  change, what is not done, and the checks at your confirm).
- **Remove from NetBox…** does the same for a removal: every object it would delete, and what
  each deletion takes with it. Its card also offers **Stop tracking instead…** (below). When an
  object could not be read, or what a deletion takes with it could not be established, the
  card says **Remove is not offered** and why, with **Read again**
  ([how](netbox-import#remove-preview)).
- **Import every network…** previews one import of them all.

One device is imported from its own page: the device page's NetBox tab has **Import into
NetBox…** for that device alone, the same preview and confirm, used to bring its record up to
its committed golden after its intent is deployed. Needs attention names each device whose
golden holds more than NetBox. An import also makes the cables LLDP shows between managed
devices, from both ends' reports as the Topology reader last stored them. It reports every
other neighbour, never inventing one ([cables](netbox-import#cables)).

Confirm with **Import** or **Remove** (busy as **Starting the import…** or **Removing…**): the plan is recomputed and compared, the one-shot
confirmation is used, and only then are writes turned on if you asked for that. An import then
runs on, and its card fills in with each network's result when it ends. Each import, Remove
and Stop tracking is also a **NetBox** row on the network's [History](history) timeline. See
[Import into NetBox, or remove](netbox-import).

## Stop tracking {#stop-tracking}

**Stop tracking instead…**, on a Remove card, is for objects that should stay in NetBox but no
longer be {{product}}'s: it deletes nothing in NetBox. Its own preview names the count and each
object {{product}} would forget, by type (collapsed under its count when the list is long), and
says where the data survives. NetBox keeps every object, with its `nmas-managed` tag, and the
removal record keeps who forgot which entries and when (the network's Removals). It also says
what cannot be taken back: Remove can never act on these objects again, and a later import only
updates them. Delete them in NetBox itself if they should go. The network's last import result
is cleared from this page; what {{product}} modified and adopted in NetBox is not changed. When
{{product}}'s record holds nothing it created for the network, the preview says there is
nothing to forget and offers no confirm.

Confirm with **Stop tracking**. Nothing is written to NetBox, so no writes switch is drawn. The
record is read again and compared with the preview's; if it changed (an import recorded
another object, say), nothing is forgotten and you preview again. See
[Stop tracking](netbox-import#stop-tracking).
