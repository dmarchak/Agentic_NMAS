# Configure a switch's OpenFlow from NetBox

Mercury configures each switch's OpenFlow section from what NetBox says: its controller's address
and port, the OpenFlow version, transport and fail mode, the OpenFlow instance and its ports. It
reads those values from the network's committed NSOT export, renders the switch's template, and
sends the lines only after you confirm the exact program by its hash. You start it from
[SDN › Switches](sdn-switches) with **Configure from NetBox…**, or **Preview the fix…** on a
switch's row. Arista EOS, ArubaOS-Switch and Open vSwitch are configured this way; Comware and
AOS-CX templates are rendered and never sent.

![Configuring a switch's OpenFlow from NetBox: the values are read from the network's committed NSOT export; the switch's version and running configuration are read, parsed, and the template rendered against them, with the undo that puts back exactly what the program changes and the hash over both and the export's; you confirm by that hash; refused unless the template is confirmed, planned again and the hash compared, the switch held while its lines are sent; verified on the switch and in the controller's switch list; the undo sent on a failure; recorded. Nothing is saved to the startup configuration.](diagrams/openflow-config.svg)

## The steps

1. `values`: the switch's OpenFlow values are read from the network's committed NSOT export,
   never from NetBox live. A network with no committed export is refused, naming the NSOT export
   card on [SDN › Apps](sdn#apps); a missing or ill-shaped value is refused naming it and where
   in NetBox it comes from, and nothing is read from the switch.
2. `read before`: Mercury reads the switch's `show version` (its release chooses the platform
   profile, which says which OpenFlow versions it offers) and `show running-config`, both reads
   on its capture list. The configuration is parsed into its OpenFlow layer; the text itself is
   never kept. An Open vSwitch server's bridge is read by its `ovs-vsctl` reads instead.
3. `render`: the switch's template is rendered against what it holds now, so an Arista whose
   bound ports change restarts its OpenFlow agent and one whose binding stays does not. A
   program that would leave the switch still differing from NetBox (a second controller the
   template cannot remove, say) is refused, naming what would remain.
4. `undo`: the lines that put back exactly what the program changes, and nothing else. Mercury
   checks them by parsing the configuration as it would be after the program and the undo: it
   must read as it does now, or nothing is sent.
5. `hash`: over the switch, the template, the program, the undo, the parsed before and the
   export's hash. The preview shows the program, the undo and this hash.
6. `hold`: once you confirm, the template must be confirmed on the network, the plan is made
   again and its hash compared (a switch or an export that moved sends nothing, naming both
   hashes), and the switch is held, across every Mercury process, for the send.
7. `send`: the lines go in one configuration set (one OVSDB transaction on Open vSwitch). The
   session carries only the template's line shapes while the switch is held: no save, no other
   line.
8. `verify`: the running configuration is read back and its OpenFlow layer must be the
   program's; then the controller's switch list must hold the switch's datapath id within six
   reads two seconds apart.
9. `rollback`: on a line the switch refused or a failed check, the undo is sent and the switch
   read again; the result says whether it reads as it did before.
10. `record`: the run is kept in the network's SDN operation record, and History shows it as
    "OpenFlow configuration on <switch>".

## The preview {#preview}

**Configure from NetBox…** previews the switches you ticked, or every one that is not connected
as intended; **Preview the fix…** previews one. Each switch shows its release, its exact
program, what differs now, the defaults used, any interface left out of OpenFlow (the management
interface never is one), what Verify checks, its undo (folded) and its hash. A switch already as
intended says so and sends nothing. A switch on a draft template, or whose plan was refused, is
listed under **Not sent** with why. Reading the preview writes nothing.

## The confirm {#confirm}

**Configure N switch<es>** (Configure 1 switch, Configure 2 switches) is a verified person's and is bound to the preview's hash. Each switch
is planned again and its own hash compared, so a switch that moved is refused by itself, naming
both hashes, while the others go on.

## Verify now {#verify-now}

**Verify now** asks the controllers for their switch lists again now, as the SDN reader does
every 30 seconds; the tab redraws when it has. It sends nothing to a switch.

## The result {#result}

The card says how many were configured, and per switch what was sent, each check of Verify and
the outcome: verified, rolled back (with whether it reads as before), or not configured with
why. **Open the record** opens History; **Back to Switches** closes the card.

**Nothing is saved to the startup configuration.** Whether this operation saves is undecided,
so the running configuration holds the change until the switch reloads, and the result says so.

## The templates, and confirming one {#templates}

A template is a draft on a network until a verified person confirms it against a saved capture
of one of its devices (a `show running-config` read on [Show commands](show-commands-screen)).
**Confirm against a capture…** shows the template's lines, each with its citation and why,
beside the capture; **Confirm <template>** commits `openflow_confirmations/<template>.yml` in the network's
repository as you, naming the capture and both hashes. A template that changes is a draft again.
Only a confirmed template is ever sent.

## IPv6

Arista EOS and ArubaOS-Switch take an IPv4 controller only (their vendor documents): an IPv6
`openflow` Service address is refused at the preview, named. A switch managed over IPv6 is read
and configured over its IPv6 session. Open vSwitch takes an IPv6 controller.
