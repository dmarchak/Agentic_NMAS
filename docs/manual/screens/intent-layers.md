# Intent (layers)

The network's intent layers: values several devices share, written once. A layer is for the
whole network, or for one site, role or tag the inventory gives its devices (NetBox's, read
with the inventory). Each is one file in the network's intent repository
(`layers/network.yml`, `layers/site-<slug>.yml`, `layers/role-<slug>.yml`,
`layers/tag-<slug>.yml`), committed as a device's intent is. The page reads only what is
committed, and it writes nothing.

## How layers merge {#merge}

What a template renders for a device, and what a deploy sends, is its layers merged, then
the device's own intent: network first, then site, role and tag, then the device, a later one
winning. A section of settings merges setting by setting; a list of named entries (accounts by
name, VLANs by number, SNMP hosts by address) merges entry by entry, so a tag's account joins
the device's own accounts; a single value, or a list of plain values such as the NTP servers,
from a later layer replaces an earlier one whole. An empty value never replaces one.

A layer carries only what several devices can share: never `interfaces` or `routing`, which
describe one device's cabling, and never a secret's value, only its reference. Two layers of
one rank (two tags a device carries) that set one value differently cannot be merged: nothing
picks between them, so the devices that take both render nothing until one layer changes. The
page lists each such value above the layers, naming both layers, both values and the devices.
A network with no layer renders exactly as before.

## The page {#page}

The layers, in merge order, on the left: each with how many devices it reaches and how many
values it sets. The chosen one, on the right: the group it follows and its devices (the names,
or a count that opens to them past twelve), its file and the commit that last changed it, and a
table of its values. **Devices it reaches** counts the devices whose render takes each value,
and names each device that overrides it, by its own value ("this device") or a later layer.
The secret references the layer names are listed with what each is for; a value is held per
device and set on each device's Intent tab, under Secret references, which lists a layer's
references beside the device's own.

When the inventory cannot be read, the page says so and counts no device in any layer: no
group is taken from an earlier read. The page re-reads when intent is committed.

Each device's own Intent tab shows the other side: which layers it takes and where each of its
values comes from (see [the device page](device-page#intent)).

## Changing a layer {#change}

**Edit…** beside a value, **Add a value…** below them and **Add a layer…** under the list open
the change's form above the layers; **Plan the change** plans it for every device the layer
reaches and draws the plan in place, sending nothing and writing nothing (see
[Plan a layer's change](fleet-change)).

Below the plan, **Approve and run: canary first** commits the layer once and runs the change,
the canary first, then batches, the first failure stopping it (see
[the approval and the run](fleet-change#run)).

## Not yet {#not-yet}

Removing a value comes after a removal's shape is measured on each platform. A stopped run
does not yet raise a Needs attention row, and the run's card does not yet offer Plan again,
Undo or the record: each device's receipt is on its History.
