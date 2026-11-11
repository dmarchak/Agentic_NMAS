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
   template cannot remove, say) is refused, naming what would remain. An Arista's OpenFlow
   ports are all sent in one `bind interface` line ([why](#arista-bind)).
4. `undo`: the lines that put back exactly what the program changes, and nothing else. Mercury
   checks them by parsing the configuration as it would be after the program and the undo: it
   must read as it does now, or nothing is sent. On an Arista whose bound ports change, the
   undo takes the program's ports out in one line and binds the ports it bound before in one
   line.
5. `hash`: over the switch, the template, the program, the undo, the parsed before and the
   export's hash. The preview shows the program, the undo and this hash.
6. `hold`: once you confirm, the template must be confirmed on the network, the plan is made
   again and its hash compared (a switch or an export that moved sends nothing, naming both
   hashes), and the switch is held, across every Mercury process, for the send.
7. `send`: the lines go in one configuration set (one OVSDB transaction on Open vSwitch). The
   session carries only the template's line shapes while the switch is held: no save, no other
   line. A switch already as intended is sent nothing: for a vendor switch its running
   configuration's OpenFlow layer is already the program's, and for an Open vSwitch bridge
   every one of Verify's checks of the bridge already passes before the send. Verify still
   runs.
8. `verify`: the running configuration is read back and its OpenFlow layer must be the
   program's; then the controller's switch list must hold the switch's datapath id within six
   reads two seconds apart. On an Arista, Mercury then reads `show openflow` and compares the
   interfaces its OpenFlow agent binds with the program's, within six reads two seconds apart:
   a set that differs fails Verify, naming both sets (intended, and what `show openflow`
   lists). If that answer cannot be read, the check neither passes nor fails: the outcome is
   unverified, what was sent stays, and nothing is rolled back.
9. `rollback`: on a line the switch refused or a failed check, the undo is sent and the switch
   read again; the result says whether it reads as it did before.
10. `record`: the run is kept in the network's SDN operation record, with what it was built
    from and each value it changed, and History shows it as "OpenFlow configuration on
    <switch>", the switch in its Device column.

## The preview {#preview}

**Configure from NetBox…** previews the switches you ticked, or every one that is not connected
as intended; **Preview the fix…** previews one. Each switch shows its release, its exact
program, each value the program changes (before → after), the values it was built from and
where each came from, the defaults used, any interface left out of OpenFlow (the management
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

The card says how many were configured, and lists every switch at full height:

- **Sent**: how many lines, or one transaction, with the exact lines under *What was sent*; or
  "already as intended, nothing sent" where nothing changed.
- **Before → after**: each value the program changed, as the switch held it and as it holds
  it now. A run that was rolled back says its changes were sent, then put back.
- **Verify**: how many checks passed and how long Verify took, and when. Each check's own
  words, the operation's id and the switch's datapath id are under *Details for the record*.
- **Outcome**: verified, rolled back (with whether it reads as before), unverified (nothing
  was sent and a check failed, or a check could not be read; what the switch holds stays), or
  not configured with why.
- Under each switch, **what its program was built from**: the committed NSOT export (a link
  to its card on SDN › Apps) and the commit that wrote it (a link to that commit on History),
  then each value with where it came from, as Mercury resolved it: the controller's address
  and port from the NetBox Service `openflow` on its device (and whether the address is the
  Service's own or its device's primary IPv4 or IPv6); the version, transport and fail mode
  from the device's config context, or Mercury's default where the context gives none; the
  instance; the datapath id from the custom field `openflow_datapath_id`, or read from the
  switch where that is empty; the ports from the interfaces tagged `openflow`, and their
  numbers. An NSOT export keeps a device's rendered config context, not which context object
  supplied a key, so the context is not named.

**Open the record** opens History, where each switch's row says the same: the switch in the
Device column, what was sent and the outcome in one line, what it was built from and each value
before and after when the row is opened, and its identifiers under *Details for the record*.
**Back to Switches** closes the card.

**Nothing is saved to the startup configuration.** Whether this operation saves is undecided,
so the running configuration holds the change until the switch reloads, and the result says so.

## An Arista's bound ports, in one line {#arista-bind}

An Arista's OpenFlow agent takes the interfaces its `bind interface` configuration names.
Whether a second `bind interface` line adds its interfaces to that set or replaces the set has
not been measured on the lab's release (EOS 4.17.0F), so Mercury sends every OpenFlow port in
one line, which gives the same set either way: `bind interface Et18-19` for Ethernet18 and
Ethernet19, the form the switch's own configuration holds, or `bind interface Ethernet18` for
one port.

- **Ports that are not one unbroken range are refused at the preview.** Ethernet18 and
  Ethernet20, or breakout ports such as Ethernet1/1 beside others, have no one-line form
  Mercury has read from a switch, and it does not guess one. The refusal names the ports, the
  two forms it writes and what is wrong with the set (for example "Ethernet19 is not among
  them"). It clears when the ports NetBox tags `openflow` are one port or neighbours and the
  export is committed again (**Export from NetBox…** on [SDN › Apps](sdn#apps)).
- **A port leaving the set is refused.** If NetBox no longer tags a port the switch binds,
  the one line would either leave it bound or remove it, depending on how the switch reads
  the line, and this operation never removes. The refusal names both sets.
- **Verify reads the set back** from the switch's own `show openflow`, as step 8 says.

A changed template is a draft again, so after an update that changes it, confirm it against a
capture again before the next Configure.

## The templates, and confirming one {#templates}

A template is a draft on a network until a verified person confirms it against a saved capture
of one of its devices (a `show running-config` read on [Show commands](show-commands-screen)).
The picker offers only the captures of that read (an Open vSwitch server's is `sudo -n ovs-vsctl
show`, a Comware switch's `display current-configuration`), newest first, and starts on the
newest; where the network confirmed the template before against another read, that read's
captures come first. A template that changed is confirmed again from the same picker.
**Confirm against a capture…** shows the template's lines, each with its citation and why,
beside the capture; **Confirm <template>** commits `openflow_confirmations/<template>.yml` in the network's
repository as you, naming the capture and both hashes. A template that changes is a draft again.
Only a confirmed template is ever sent.

## IPv6

Arista EOS and ArubaOS-Switch take an IPv4 controller only (their vendor documents): an IPv6
`openflow` Service address is refused at the preview, named. A switch managed over IPv6 is read
and configured over its IPv6 session. Open vSwitch takes an IPv6 controller.
