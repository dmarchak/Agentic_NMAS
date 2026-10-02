# The model: intent, golden, device

NMAS keeps three things about every device, and almost everything it does moves one of them
toward another. Learning which operation moves which is most of learning the tool.

## The three records

- **Intent** is what the device SHOULD be: a YAML document per device, committed to the
  network's git repository (`host_vars/<device>.yml`). A change is made by editing intent and
  committing it, never by configuring the device and copying what it has.
- **The golden** is what the device WAS, the last time the tool recorded it: its running
  configuration, captured and committed (`golden/<device>.cfg`). It is a record, not a wish.
- **The device** is what IS, right now. Nothing the tool stores can be trusted to equal it
  without reading it again.

![Intent, golden and device, and the operations that move each: a deploy moves the device toward intent; a capture moves the golden toward the device; seeding moves intent from the golden.](diagrams/intent-golden-device.svg)

Three operations connect them, and each moves exactly one record:

- **Deploy** moves the device toward intent (see [Deploy a change](deploy)).
- **Capture** (and its fleet form, Save All) moves the golden toward the device (see
  [Capture and Save All](capture)).
- **Seed** moves intent from the golden, once, for a device that has no intent yet (see
  [Seed intent](seed)).

## Everything is read from what is committed

Every reader takes intent and goldens as COMMITTED in git, never a file edited on the host's
disk. A file nobody committed governs nothing, so the record you can see in History is the
record the tool acts on.

## Merge, not replace

A deploy ADDS the lines intent has and the device lacks, and changes nothing else. A line the
device has and intent lacks is reported as residue and left in place. Removing a line is its
own operation, chosen line by line (see [Remove a line (Mode B)](removal)).

![Merge versus replace: a merge sends only the lines intent has and the device lacks, and leaves the device's other lines in place; a replace would remove every line intent does not name, which NMAS never does.](diagrams/merge-vs-replace.svg)

## Preview, confirm, result

Every operation that changes a device or the record works the same way:

1. **Preview.** The tool computes exactly what it will send and record, reading what it needs
   now, and shows it: the program, the gates it checked, and what it will NOT do.
2. **Confirm.** You confirm that preview. The confirm is bound to a hash of what you saw: if
   anything moved between the preview and the confirm (the device, intent, a template), the
   tool refuses and sends nothing, and you preview again.
3. **Result.** What happened, device by device, drawn from the record the operation wrote,
   so you can find it again later in History.

## A baseline is a moment

A baseline tag (`baseline/<time>`) names one commit at which every device's golden and
intent were recorded, and says what that moment EARNED: whether every device was measured at
its committed intent.

![What a baseline contains: one commit holding every device's golden and every device's intent, named by the tag baseline/<time>, with what it earned recorded on the commit.](diagrams/baseline-contents.svg)

Re-applying a baseline sends each device what it lacks from that moment (see
[Restore and re-apply a baseline](restore)). Credentials are always the ones held NOW:
a baseline older than a rotation would otherwise put back a password the rotation retired.

## Who did it

Every commit carries an `Actor:` and how that actor was established
(`Actor-Verified: access` for a person signed in through the tunnel, `host-shell` for a
command run on the host). Anything that changes a device or exposes a secret has a person
behind it.
