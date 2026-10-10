# NetBox

Importing each network into NetBox, and removing what {{product}} put there: the sidebar's
**NetBox**. Nothing on this page reaches a device.

## What it is for {#what-it-is-for}

- **Import** builds NetBox's records from each device's committed golden. It previews every
  object it would create or change, and confirming is one-shot: it is refused if NetBox
  changed since the preview.
- **Remove** deletes only what {{product}} created (tagged AND in {{product}}'s own record), and names
  everything a deletion would take with it.
- **Writes are off unless switched on.** A confirm here can turn them on, with your permission,
  and they come on only once its token and plan both pass; they are turned off on
  Settings › Installation's NetBox card. Every write records who and on what basis.

## Connection {#connection}

Whether NetBox answers (the integrations reader's last read, every minute) and whether writes are
on for every network. If NetBox is not configured, its address and token are set on
Settings › Installation › Connections, and nothing here runs until they are.

## Networks {#networks}

Every network, with its devices, its last import's result (complete, PARTIAL or FAILED, never
green over a partial) and how many removals are recorded for it (each opens as it was drawn at
its apply).

- **Import into NetBox…** starts a dry run of the real import against the real NetBox, writing
  nothing. It takes about a minute on a lab, so it runs as a job: its card, below the table, says
  what it is doing, and fills in with the preview when it is ready (every object to create or
  change, what is not done, and the checks at your confirm).
- **Remove from NetBox…** does the same for a removal: every object it would delete, and what
  each deletion takes with it.
- **Import every network…** previews one import of them all.

Confirm with **Import** or **Remove**: the plan is recomputed and compared, the one-shot
confirmation is used, and only then are writes turned on if you asked for that. An import then
runs on, and its card fills in with each network's result when it ends. See
[Import into NetBox, or remove](netbox-import).
