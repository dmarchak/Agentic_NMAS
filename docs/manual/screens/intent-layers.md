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
device and set on the device's Intent tab, which does not yet offer a reference only a layer
names.

When the inventory cannot be read, the page says so and counts no device in any layer: no
group is taken from an earlier read. The page re-reads when intent is committed.

Each device's own Intent tab shows the other side: which layers it takes and where each of its
values comes from (see [the device page](device-page#intent)).

## Not yet {#not-yet}

Adding a layer, editing or removing a value and planning a layer's change for its devices come
with fleet changes' plan (one change, each device's preview, one approval, a canary). Until
then Mercury cannot add or change a layer: this page shows the layers a network has.
