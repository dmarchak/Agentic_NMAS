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
file, or `(absent)` for a setting not there. **Add a setting** adds another row, keeping what
you typed (up to twelve). **Plan the change** starts the plan; **Cancel** returns to the layer.

From **Devices**, tick the devices and choose, under Actions, **Change across the (<count>) ticked…**: the same
form opens for those devices. Under **Where**, choose each device's own intent (the default:
the change is made in each ticked device's own intent file, and a device holding something
other than the value now is refused by name) or a layer every ticked device takes (the layer's
change, which may reach devices beyond the ticked; the plan names each). The plan, the approval
and the run are the same as a layer's; for each device's own intent, the commit is one commit of
every ticked device's file that takes the change. **Cancel** returns to Devices.

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

Nothing in the plan is sent or written. **Back to** the layer returns to it; a change that was
refused names why and offers **Back to the layers**.

## The approval and the run {#run}

Below the plan, choose the **Canary** (one of the planned devices, the first by default), the
size of the batches after it (**Then batches of**, one by default), and **After the canary**:
pause for your review (the default) or go on. Give a one-line **Summary** (the commit's
subject) and **Why**, then **Approve and run: canary first**, as a verified person.

When no device's program changes (each device already holds the value, as when a value moves
from each device's own intent into a layer), the plan says **Nothing to send** and offers
**Approve and commit: nothing to send** instead: the approval commits the layer once and the
run sends nothing, its card reading "Committed, and nothing was sent". A layer the change would
leave as it is has nothing to commit, and the plan offers no approval.

5. **The approval.** Read: everything the plan read, again, under the repository's lock. Sent:
   nothing. Recorded: one commit of the layer's file (`Source: fleet-change`, who, the summary,
   the reason, the plan's hash and the devices). The plan is made again; a hash that is not the
   one you approved refuses the run, naming both, nothing committed or sent.
6. **The canary.** Read: the canary's program as committed, which must be the one approved.
   Sent: its program, through the deploy every device takes (held, sent, verified, rolled back
   on its own if it fails). Recorded: its receipt. The card draws each device's step, outcome
   and why as it goes.
7. **The batches.** After a pause, the card names the devices left and offers **Go on: the N
   left** (a verified person's decision, each device's program checked again before it is
   sent) or **Leave it paused**, which sends nothing more: the layer stays committed, so those
   devices show intent unmet until they run. The first device that does not deploy and verify
   stops the run; the devices after it are not attempted, and the card says which. A finished
   run offers **Back to the layers**.
