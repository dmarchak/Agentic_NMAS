# NetBox

Importing the network into NetBox, and removing what {{product}} put there. The sidebar item opens
today's NetBox tab until the redesign builds it (plan 7.6).

## What it is for {#what-it-is-for}

- **Import** builds NetBox's records from each device's committed golden. It previews every
  object it would create or change, and confirming is one-shot: it is refused if NetBox
  changed since the preview.
- **Remove** deletes only what {{product}} created (tagged AND in {{product}}'s own record), and names
  everything a deletion would take with it.
- **Writes are off unless switched on** in Settings, and every write records who and on what
  basis.
