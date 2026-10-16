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
whose inventory is NetBox, NetBox's, marked "from NetBox"), its last import's result (complete, PARTIAL or FAILED, never
green over a partial) and how many removals are recorded for it (each opens as it was drawn at
its apply).

- **Import into NetBox…** starts a dry run of the real import against the real NetBox, writing
  nothing. It takes about a minute on a lab, so it runs as a job: its card, below the table, says
  what it is doing, and fills in with the preview when it is ready (every object to create or
  change, what is not done, and the checks at your confirm).
- **Remove from NetBox…** does the same for a removal: every object it would delete, and what
  each deletion takes with it. Its card also offers **Stop tracking instead…** (below).
- **Import every network…** previews one import of them all.

Confirm with **Import** or **Remove**: the plan is recomputed and compared, the one-shot
confirmation is used, and only then are writes turned on if you asked for that. An import then
runs on, and its card fills in with each network's result when it ends. See
[Import into NetBox, or remove](netbox-import).

## Stop tracking {#stop-tracking}

**Stop tracking instead…**, on a Remove card, is for objects that should stay in NetBox but no
longer be {{product}}'s: it deletes nothing in NetBox. Its own preview names the count and each
object {{product}} would forget, by type (collapsed under its count when the list is long), and
says where the data survives. NetBox keeps every object, with its `nmas-managed` tag, and the
removal record keeps who forgot which entries and when (the network's Removals). It also says
what cannot be taken back: Remove can never act on these objects again, and a later import only
updates them. Delete them in NetBox itself if they should go.

Confirm with **Stop tracking**. Nothing is written to NetBox, so no writes switch is drawn. The
record is read again and compared with the preview's; if it changed (an import recorded
another object, say), nothing is forgotten and you preview again. See
[Stop tracking](netbox-import#stop-tracking).
