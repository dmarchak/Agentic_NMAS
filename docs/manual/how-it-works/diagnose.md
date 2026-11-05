# Diagnose: a runbook's reads, ranked into hypotheses

**Diagnose…** on a device's Actions menu runs one of two fixed runbooks: "an adjacency is down
with both ends at intent" and "can't reach a device or an address". The same Diagnose… is on an
alert's evidence pack (Monitoring › Alerts, above Explain) and on a can't-fix row of Needs
attention, any tier, Never's included; each opens the device's card with its runbook and target
taken from what raised it (see [Where it opens from](#from)). A runbook is a list of
steps in code. Each step is a read of a device, or a comparison of what was read with committed
intent. It sends no command that is not a read, changes nothing, and calls no model. What it
answers is a **diagnosis**: each step with its result, the hypotheses ranked with their
evidence, and the checks that passed.

![Diagnose: a person picks the runbook and its target from intent, and the card lists every read on each device before anything is asked; the plan is made again at the press and refused if it moved; each device is held for the diagnosis, one at a time per device, and read through the reads engine, read-only, its counters read twice; the logs of the last hour are read from Loki; what was read is compared with intent by the rule table, and the hypotheses are ranked; the diagnosis is recorded, and the card draws it. Nothing is changed on any device.](diagrams/diagnose.svg)

## The card

The card opens in place of the tab. Choose what is wrong, then its target:

- **An adjacency is down:** one of the device's intended neighbours, from intent. A link intent
  holds is offered with its protocols ("edge2 over Gi4: OSPF, area 0 (intent)"); a BGP neighbour
  intent names, with its AS. An adjacency whose plan cannot be made is listed under "not
  offered", with why (intent runs no OSPF, OSPFv3 or BGP over the link, for one).
- **Can't reach:** a device of the network, by its loopback address in intent, or an address
  you give. An address is checked as one IPv4 or IPv6 address. "Can't reach" follows IPv4
  forwarding only (`show ip cef`): an IPv6 address is refused by name, with nothing read, until
  `show ipv6 cef` is captured and parsed.

Before anything is asked, the card lists every read the run will make on each device, the
reads it makes at each hop for "can't reach", the logs it reads, its count against the cap of
70 device commands, and the worst case by the reads' own bounds. **Run the diagnosis** needs a
verified person, because what it reads is shown to the person who asked. The plan is made
again at the press; if the reads moved since the card was drawn (intent changed), nothing is
read and the card says so, naming both fingerprints.

If a device the plan reads is already in a diagnosis, the card says so in place of the button
("edge1 is in diagnosis dg-... (started 18:40 UTC by ...); Diagnose… is offered when it ends"),
and draws itself again when a diagnosis ends. It asks without taking the device: the press
still refuses by name if a diagnosis starts between the card and the press.

## Where it opens from {#from}

- **The device's Actions menu:** the card on its first choice.
- **An alert's evidence pack:** an alert naming an interface opens "An adjacency is down" with
  the adjacency over that interface chosen; "Device unreachable" opens "Can't reach" on the
  first of the device's neighbours by intent, the unreachable device the target (by its
  loopback in intent); any other alert opens the card on its first choice. A pack naming no
  device (an SDN detection's) says Diagnose… is not offered, and why.
- **A can't-fix row:** the same, from the incident's first trigger (an alert, or an
  adjacency's other end).

If what raised it names an adjacency the card does not offer, the card says so and chooses the
first. Nothing is read until you press **Run the diagnosis**.

## The steps: an adjacency is down

1. `plan`: both ends of the adjacency from intent and the network model: each end's interface,
   its addresses on the link, its OSPF and OSPFv3 area and the BGP session over it; every read
   on each end. At most 14 reads a device.
2. `hold`: both ends are held for this diagnosis. One diagnosis at a time per device: a device
   already in one refuses this one by name ("not diagnosed: edge1 is in diagnosis dg-..."), never
   queued.
3. `read`: both ends at once, through the reads engine, as reads of kind diagnosis: each held
   while it is read (a device another operation holds is skipped and named), masked, and a run
   on History › Reads.
4. `read again`: the interface counters a second time, 10 s later. The difference is the
   evidence of errors rising; counters are never cleared.
5. `logs`: each end's configuration lines logged in the last hour, from Loki.
6. `compare`: what was read against intent, rule by rule (shut, down while up, cabled elsewhere,
   errors, MTU, subnet, OSPF's area, timers, network type and authentication, passive, one way,
   BGP's state and remote AS, an access list, a configuration change).
7. `rank`: decisive before strong before circumstantial; within a strength, bottom-up by layer;
   then by how many reads agree. A hypothesis whose evidence is incomplete ranks below every
   complete one of its strength, naming the read it lacks. At most five are shown.
8. `record`: the diagnosis is one record in the self-healing step log, masked.

## The steps: can't reach {#reach}

1. `plan`: A is the device, B the address; B's device is the one intent says holds it. An
   address no device holds is outside management: the path is followed as far as the network's
   devices, then a traceroute.
2. `hold`: A is held, then each device as the path reaches it.
3. `reach`: A pings B, from its loopback when intent gives it one.
4. `trace`: the path is followed device by device with `show ip cef` for B.
5. `hop`: at each routed hop, in order: the egress interface, its `show ip interface`, the next
   hop's ARP entry, the route, the next hop's ingress interface, and a bound access list's
   counters. The run stops at the first hop that diverges from intent, and names the hops it
   did not check.
6. `read again`: each hop's egress interface a second time, 10 s later.
7. `traceroute`: when the path leaves the network toward an address no managed device holds.
8. `return`: from B's device back to A, when the forward path holds and B is managed.
9. `logs`: each device read: its configuration lines in the last hour, from Loki.
10. `compare`, `rank` and `record`: as for an adjacency, with this runbook's rules (a hop down,
    protocol down, errors rising, the next hop unresolved, no route, a loop, the path leaving the
    network, no return path, an access list intent does not hold, a configuration change). At
    70 commands it stops and says where: about nine hops.

## The result

The diagnosis is drawn in the card's place when the run ends: its headline (how many
hypotheses, the first one's strength), each hypothesis with its layer, strength, evidence and
what would rule it out, each piece of evidence a link to its read's run on History › Reads
(the masked answer), what was ruled out, what was not checked and why, and every step. With no
rule firing it reads "no cause found in what Mercury reads", then the ruled-out list. It never
guesses. **Run again…** opens the card again.

For "can't reach", **The path, hop by hop** comes first: the ping (sent, its answer on History ›
Reads, not interpreted until it has a capture), each hop checked with what was read and "as
intent" or "diverges here", and the devices after the hop that diverges "not read". The
headline then names the hop ("diverges at edge2").

**Open in History** opens the device's History tab on the kind Diagnoses and the day it ran:
each diagnosis a person ran is a row there, and on History, on every device it read. A
diagnosis self-healing runs for an incident is that incident's, on its row. Leave the page
while it runs, and the device's page opens the card again when you come back, until you have
seen its result; the top bar's In progress lists it meanwhile.

"Diagnosed" is not a fix: a diagnosis on demand acts on nothing and clears nothing.

## What it never does

It sends no configuration command, no `clear counters`, no `send log` and no `terminal`
setting: every command passes the reads engine's read-only allowlist with nothing added. It
calls no AI model. It reads no device that is not part of the adjacency or the path.
