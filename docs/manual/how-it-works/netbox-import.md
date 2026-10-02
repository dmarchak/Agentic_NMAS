# Import into NetBox, or remove

The import writes a device list into NetBox, built from each device's committed golden: a
region and a site for the list, each device with its interfaces, addresses, prefixes, VLANs,
VRFs and static routes. Remove deletes what the import created, and only that. Both are
previewed by a dry run against the real NetBox and confirmed once; no device is reached and
nothing in git changes.

![The NetBox import and remove: a dry run reads NetBox and plans every write; the plan's hash is bound to a one-time confirmation; the confirm recomputes the plan and writes only if it is unchanged; every create is tagged nmas-managed and recorded, every update recorded with its before and after; Remove deletes only what is both tagged and recorded, after asking NetBox what each delete takes with it.](diagrams/netbox-import.svg)

## Two conditions for any write {#conditions}

Every write the tool makes to NetBox passes through one of three chokepoints (create, update,
delete), and each refuses unless both hold:

- **The master switch**, `netbox_allow_writes`, is on. It means "this instance may write to
  NetBox at all", is off by default, and is a saved setting (Settings, Integrations, or the
  "Permit NetBox writes" box in the confirm dialog). Turning it on does not approve any
  operation.
- **The write declares its authority**: the confirmation it stands on. For the import and
  Remove that is the NetBox tab's one-time confirmation, by the person who gave it. A write
  that names no authority is refused where it happens.

A dry run is always allowed, because it writes nothing.

## The import: preview {#preview}

1. **Read the list's inventory.** Read: every device in the chosen list (or in every list,
   for import-all). Sent: nothing. Recorded: nothing. A list with no devices is refused.
2. **Read each device's committed golden.** Read: the golden as committed in git, never the
   device. Sent: nothing. Recorded: nothing. A device with no golden, or one the tool refuses,
   is reported with its reason and not imported.
3. **Run the real import with every write captured.** Read: NetBox, every lookup the real
   import makes. Sent: nothing to a device, nothing written to NetBox. Recorded: nothing; a
   preview does not overwrite the record of the last real import. Each create is planned with
   a placeholder id, and a shared object is planned once, not once per device. Each update
   reads the object as NetBox holds it first, so the plan says which fields it changes, or
   that it changes nothing. This is why the preview count is the executed count.
4. **Bind a one-time confirmation to the plan.** Read: nothing. Sent: nothing. Recorded: a
   confirmation held in the tool's memory, bound to a hash of every planned create and update
   and to this operation and list, valid for 5 minutes and usable once.
5. **Draw the preview.** Each create and update by name, the fields each update changes (never
   their values), the updates that change nothing, what was deliberately not modelled (for
   example addresses in an excluded VRF, `netbox_excluded_vrfs`), and the gates.

## The import: confirm and apply {#apply}

1. **The permit box, if ticked.** Recorded: `netbox_allow_writes` turned on, as a saved
   setting. This is the only thing the box does.
2. **The master switch** is checked. If it is off, the confirm is refused and nothing is
   written.
3. **The confirmation is consumed.** It is spent whether or not it is valid, so it can never
   be replayed. A refusal says which case it was: already used, expired (with its times), or
   not one this server issued (the server restarted since the preview).
4. **The plan is computed again** with a second dry run, and its hash compared with the one
   confirmed. If NetBox changed in between, nothing is written: preview again.
5. **The import runs** in the background, shown on the in-flight panel. Read: NetBox. Sent:
   nothing to a device. Recorded: in NetBox, the region, site, config template and list VRF,
   then each device one after another (devices share objects that are created on first use,
   so they are written in order). Each write carries the person who confirmed and the
   confirmation it stands on.
6. **The result is recorded** as the list's import record, which the NetBox tab's card draws:
   devices created and updated, every write that did not land (`complete` is false if any),
   what was skipped, and the notes (for example a site the tool did not create, which it uses
   and does not move).

## What each write records {#records}

Four records, each answering one question, kept apart so that none can be read as another:

- **Created** (`netbox_created_ids.json`): every object the tool created, per list, with who
  and on what authority. Every object created on a taggable endpoint (regions, sites, devices,
  interfaces, VRFs, prefixes, VLANs, addresses, tunnels) also carries the tag `nmas-managed`.
  A create whose tag cannot be ensured is refused, because an untagged object is one Remove
  can never act on.
- **Modified** (`netbox_modified.json`): every update, with each changed field's value before
  and after, masked, with who and on what authority. An update that changes nothing records
  nothing; one whose before-state could not be read is recorded as unknown. An update never
  tags an object and never makes it removable.
- **Adopted** (`netbox_adopted.json`): objects that already existed when a device was
  [adopted](adopt). Written by adoption, never by the import, and never removable.
- **Removed** (`netbox_removals.jsonl`): every Remove, what it deleted, left alone and could
  not delete, and who.

## Remove: preview {#remove-preview}

1. **Read what the tool created for this list.** Read: the created record. Sent: nothing.
   Recorded: nothing. If it holds nothing, nothing is safe to remove, and the preview says
   that objects created before the record existed must be removed in NetBox.
2. **Read each recorded object from NetBox**, innermost first (tunnels, addresses, prefixes,
   VLANs, interfaces, devices, VRFs, sites, regions). Read: the object by id. Sent: nothing.
   Recorded: nothing. Each lands in one place:
   - *could not be read*: not gone, so neither deleted nor forgotten, and the preview cannot
     be confirmed;
   - *already gone* (NetBox answered 404): named; only a real Remove drops it from the record;
   - *no `nmas-managed` tag*: left alone, treated as a person's;
   - *tagged and recorded*: planned for deletion.
3. **Ask NetBox what each delete takes with it.** Read: the objects that hang off each planned
   delete. Sent: nothing. Recorded: nothing. NetBox deletes some objects with their parent
   (an interface takes its addresses; a device takes its interfaces). The preview names each,
   and names in capitals any the tool did NOT create. For a type whose behaviour has not been
   measured (tunnels, prefixes, VLANs, VRFs, sites, regions) it says so, which is not the same
   as nothing.
4. **Bind a one-time confirmation** to a hash of the planned deletes, as for the import.

## Remove: confirm and apply {#remove-apply}

The permit box, the master switch, the confirmation and the recomputed plan work as for the
import. Then each planned object is deleted, in order. A deleted object, and one NetBox says
is already gone, is dropped from the created record; a delete NetBox refuses is named with its
reason and stays recorded. The removal is written to the removal record and drawn from it, so
it can be read again from the NetBox tab.

**Just stop tracking** is the other choice in the same dialog: it deletes nothing, and the
tool forgets what it created for the list, so NetBox keeps every object. Those objects keep
their `nmas-managed` tag but are no longer recorded, so Remove can never act on them again.

## What the import and Remove do not do {#not}

- The import deletes nothing. Remove is its own operation.
- Neither reaches a device: everything is built from committed goldens.
- Nothing the tool only updated or adopted is ever deleted: Remove needs an object the tool
  created and tagged.
- Remove never deletes the `nmas-managed` tag itself, or every object carrying it would become
  unremovable.
- Deleting a device list never deletes NetBox objects: a list that still owns recorded objects
  is refused, naming them, until they are removed here.
- The confirm checks that NetBox has not changed the planned writes. What NetBox would take
  with a delete is asked at the preview, not again at the confirm.
