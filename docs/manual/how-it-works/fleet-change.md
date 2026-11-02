# Plan a layer's change

A fleet change makes one change to many devices through a shared intent layer: the value goes
in the layer once, and every device the layer reaches takes it (see
[Intent (layers)](intent-layers)). Planning it shows exactly what each of those devices would
be sent, before anything is committed or sent. It sends nothing and writes nothing.

![Planning a layer's change sends nothing and writes nothing. You name the layer and each setting's path, its value now and after; the layer as committed must hold the before. The devices the layer reaches come from the inventory. Each is planned twice through the deploy's own plan, as committed and with the change in memory, and the lines its program gains are its change; devices with the same change form one group, a device whose own value wins is unchanged, and one hash binds the plan. Approving and running it comes later.](diagrams/fleet-change.svg)

## Where it is {#where}

On **Source of Truth › Intent**: **Edit…** beside a layer's value opens the form with what the
layer holds there, now and after; **Add a value…** opens it with one empty setting; **Add a
layer…** asks the new layer's rank (network, site, role or tag) and its group's slug, the
inventory's own. Each setting is a path into the layer (`users`, `ntp_servers`,
`snmp.settings`), the value it holds now and the value it becomes, written as in an intent
file, or `(absent)` for a setting not there. **Plan the change** starts the plan; **Cancel**
returns to the layer.

## The plan {#plan}

1. **The change.** Read: the layer as committed at HEAD. Sent: nothing. Recorded: nothing.
   The layer must hold each setting's value now, or the change is refused naming the path, what
   the layer holds and what the change expected. The result must be something a layer may
   carry (never `interfaces` or `routing`), pass the same checks an intent edit does, and name
   no value any of its devices holds: a layer names secret references, never values.
2. **Its devices.** Read: the inventory, now. Sent: nothing. Recorded: nothing. The network
   layer reaches every device; a site, role or tag layer the devices the inventory gives that
   group. An inventory that cannot be read refuses the plan: no group is taken from an earlier
   read.
3. **Each device, twice.** Read: each device's committed golden, its intent, its other layers
   and the monitoring profile. Sent: nothing. Recorded: nothing. The deploy's own plan runs as
   committed and again with the change in place, in memory, so each device's program, checks
   and refusals are what a deploy would compute. The lines its program gains are its change;
   lines it already had pending ride along on its run and are counted apart. It runs as a job,
   and the card redraws when it ends.
4. **The plan.** Read: nothing more. Sent: nothing. Recorded: nothing. Counts first ("4
   devices, 1 group"), then the layer before and after, each group of devices with the same
   lines (collapsed past the first), the devices left unchanged with who holds the value (their
   own document, a later layer, or the device already holding it), and the devices the deploy
   refuses, each with its reasons. One hash binds the layer's before and after, the
   repository's commit and every device's program.

Approving the plan, committing the layer and running it on its devices (a canary first, then
batches, the first failure stopping it) is not built yet: the plan says so. Nothing in it is
sent or written. **Back to** the layer returns to it; a change that was refused names why and
offers **Back to the layers**.
