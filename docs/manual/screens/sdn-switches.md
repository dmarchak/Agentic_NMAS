# SDN › Switches

Every switch NetBox marks for OpenFlow (a device with an interface tagged `openflow` in the
network's committed NSOT export), joined on one row: what NetBox says it should be, what the
controller lists, and what Mercury last configured. It is a read of stored state (the committed
export, the SDN reader's last switch lists and the network's SDN operation record): opening it
contacts no switch and no controller.

## The summary

How many switches are marked for OpenFlow, and how many are connected as intended, configured
but not connected, differing from intent, changed in NetBox since they were configured, and not
configured; then the datapath ids the controller lists that no switch in the export carries
(seen by the controller, not in NetBox).

A switch **differs from intent** when its last configuration rolled back or failed. It reads
**NetBox changed since configured** when its last configuration held and was made from an
export other than the committed one: the change is NetBox's, not the switch's, and the row says
so. Under the label it names each of the switch's values that differs between the two exports,
before → after, and each export with the commit that wrote it. Where none of the switch's
recorded values changed it says the change is elsewhere in NetBox, and where the switch's record
was kept before Mercury recorded each value's source it says which value changed is not known.
The switch itself is not read for this: **Preview the fix…** reads it and shows what would be
sent. A switch is **configured, not connected** when its last configuration verified and the
controller does not list it now; **not configured** when Mercury never configured it and the
controller does not list it; **connected as intended** when the controller lists it.

## Searching and filtering

Search by name, datapath id or address; filter by state and by platform. The switches are
grouped by state, worst first, and each group shows at most 25 before it says how many more
match. Expand a switch for its NetBox values, its driver, its last configuration and that run's
checks.

## Configure from NetBox… and Preview the fix…

Both open the preview of the OpenFlow configuration in the card below the bar: tick switches to
configure only those, or leave none ticked for every one not connected as intended. See
[How it works](openflow-config#preview).

## Verify now

Asks the controllers for their switch lists now; the age beside it is the last read's. See
[How it works](openflow-config#verify-now).

## The OpenFlow templates

Each template, the network's switches on it, and its status: confirmed (by whom, when, against
which capture) or a draft, with **Confirm against a capture…**. The picker beside it offers the
network's captures of the read the template is confirmed against, newest first, and starts on
the newest: the device's configuration read (`show running-config` on Arista EOS and
ArubaOS-Switch, `sudo -n ovs-vsctl show` on an Open vSwitch server, `display
current-configuration` on Comware), or the read the network's earlier confirmation was of. A
capture of another command is not offered. With no such capture the control is greyed and says
which read to run on Show commands; if the network's saved reads can't be read it says that
instead. See [How it works](openflow-config#templates).

## IPv6

Arista EOS and ArubaOS-Switch take an IPv4 controller only, said under the bar; a switch managed
over IPv6 is listed and configured like any other.
