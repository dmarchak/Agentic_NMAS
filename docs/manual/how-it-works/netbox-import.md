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
  NetBox at all", is off by default, and is a saved setting (turned on by the "turn NetBox
  writes on with this confirm" box on a NetBox confirm, and off on Settings › Installation ›
  Connections, the NetBox connection card). Turning it on does not approve any operation.
- **The write declares its authority**: the confirmation it stands on. For the import and
  Remove that is the NetBox page's one-time confirmation, by the person who gave it. A write
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
6. **The result is recorded** as the list's import record, which the NetBox page's network row draws:
   devices created and updated, every write that did not land (`complete` is false if any),
   what was skipped, and the notes (for example a site the tool did not create, which it uses
   and does not move). The import's own record (its job, kept by the NetBox page) names who
   confirmed it and when it started and ended, and History's timeline draws it from there, as
   a **NetBox** row on the network's timeline, never another's.

Each prefix is placed at the list's site, as NetBox 4.2 and later hold a prefix's site (its
scope). NetBox answers each write with the prefix as stored, and a prefix stored without the
site sent is a write that did not land, named with both values. A prefix the tool created that
has no site yet (those created before 2026-10-16 were stored without one) is given the list's
site by the next import, previewed as an update that changes `scope_id, scope_type`. A prefix a
person made, or one already placed elsewhere, is never moved.

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
  not delete, and who; and every [Stop tracking](#stop-tracking), with each entry it forgot.
  History's timeline draws each as a **NetBox** row of its network, in the words its result
  is drawn in here.

Each of the four can be moved to the records database (Settings › Installation › Connections,
Record stores; see [The records database](records-database#move)): created, modified and
adopted as documents, removals as a log of lines. Once moved, it is kept there, and the file
named above is kept read-only for a release.

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
   measured (tunnels, prefixes, VLANs, VRFs, sites, regions), or a question NetBox did not
   answer, it says so, which is not the same as nothing.
4. **Bind a one-time confirmation** to a hash of the planned deletes, as for the import.
5. **Offer Remove only when every answer is in.** Remove is offered only when every recorded
   object was read, and what NetBox takes with each planned delete was established. Otherwise
   the card says **Remove is not offered**, with the comparison and both sides of it: for
   example, "what NetBox's database takes with each of the 4 delete(s) must be established,
   and 1 answer(s) could not be: ipam/prefixes: what a delete takes with it has not been
   measured on this NetBox". **Read again** previews the removal anew. A confirm sent without
   the card is refused the same way, and nothing is deleted. **Stop tracking instead…** stays
   offered: it deletes nothing. A check that did not establish its answer reads **not
   established**.

## Remove: confirm and apply {#remove-apply}

The permit box, the master switch, the confirmation and the recomputed plan work as for the
import. Then each planned object is deleted, in order. A deleted object, and one NetBox says
is already gone, is dropped from the created record; a delete NetBox refuses is named with its
reason and stays recorded. The removal is written to the removal record and drawn from it, so
it can be read again from the NetBox page (a network's recorded removals).

The Remove card has a second choice, **Stop tracking instead…**, which deletes nothing: see
the next section. Its third is **Close**, which leaves NetBox and the tool's records as they
are.

## Stop tracking {#stop-tracking}

Stop tracking deletes nothing in NetBox. The tool forgets the objects it created for the
network: they stay in NetBox with their `nmas-managed` tag, but no longer in the created
record, and Remove can never act on them again, because removal needs both. It writes the
tool's own record, never NetBox, so the master switch and a NetBox authority are not among its
gates. The confirmation, the re-read and the verified person are.

**Preview.** Pressing **Stop tracking instead…** on a Remove card starts its own preview.
1. **Read what the tool created for this network.** Read: the created record
   (`netbox_created_ids.json`), this network's entries only. Sent: nothing; NetBox is not asked.
   Recorded: nothing. A record that cannot be read refuses the preview, which is not the same
   as "it holds nothing". If it holds nothing, the preview says there is nothing to forget and
   offers no confirm.
2. **Bind a one-time confirmation** to a hash of exactly those entries, valid for 5 minutes and
   usable once.
3. **Draw the preview.** The count, and the counts by type. Each object by type, id and name,
   collapsed under its count when there are more than 20. Where the data survives (NetBox keeps
   every object, and the removal record keeps each entry forgotten). That nothing the tool can
   do afterwards takes it back: a later import finds these objects in NetBox and updates them,
   and an update never records an object as created. That the network's last import result is
   cleared from this page.

**Confirm and apply.** **Stop tracking** confirms as the verified person; a service or an
unverified caller is refused before anything is read.
1. **Hold the network.** One NetBox writer per network: an import or removal running for it
   refuses this, naming who, and nothing changes.
2. **The confirmation is consumed**, as for the import.
3. **The record is read again** and hashed. If it changed since the preview (an import recorded
   another object, say), the refusal names both hashes and the count now, and nothing is
   forgotten: preview again.
4. **Forget exactly the confirmed entries.** Recorded: the created record drops those entries
   and no others, so an entry added since the preview stays. The network's last import result
   is cleared.
5. **The result is recorded** in the removal record as a stop-tracking removal, with who, when
   and each entry forgotten, and drawn from it: on the card, and later under the network's
   Removals.

## What the import and Remove do not do {#not}

- The import deletes nothing. Remove is its own operation.
- Stop tracking deletes nothing and sends nothing to NetBox; it changes only the tool's
  created record, and cannot be taken back from the tool.
- Neither reaches a device: everything is built from committed goldens.
- Nothing the tool only updated or adopted is ever deleted: Remove needs an object the tool
  created and tagged.
- Remove never deletes the `nmas-managed` tag itself, or every object carrying it would become
  unremovable.
- Deleting a network never deletes NetBox objects: Settings' Delete this network… refuses a
  network that still owns recorded objects, naming them, until they are removed here.
- The confirm checks that NetBox has not changed the planned writes. What NetBox would take
  with a delete is asked at the preview, not again at the confirm.
