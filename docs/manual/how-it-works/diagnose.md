# Diagnose: a runbook's reads, ranked into hypotheses

**Diagnose…** on a device's Actions menu runs one of two fixed runbooks: "an adjacency is down
with both ends at intent" and "can't reach a device or an address". The same Diagnose… is on an
alert's evidence pack (Monitoring › Alerts, above Explain) and on a can't-fix row of Needs
attention, any tier, Never's included; each opens the device's card with its runbook and target
taken from what raised it (see [Where it opens from](#from)). A runbook is a list of
steps in code. Each step is a read of a device, or a comparison of what was read with committed
intent. Self-healing has a third runbook of its own, "a telemetry stream lost", which it runs
when a device stops streaming (see [A telemetry stream lost](#stream)). It sends no command that is not a read, changes nothing, and calls no model. What it
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
  you give. An address is checked as one IPv4 or IPv6 address. An IPv6 address is followed
  with `show ipv6 cef`, with two limits said on the result: IPv6 forwarding names a link-local
  next hop, and on a segment intent shares among several devices the path stops there, naming
  them, never guessing one; and the IPv6 access lists bound on the path are not read.

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
3. `reach`: A pings B, from its loopback when intent gives it one. When every probe is
   answered, A reaches B: the run stops there, reads nothing more, and says so.
4. `trace`: the path is followed device by device with `show ip cef` for B (`show ipv6 cef`
   for an IPv6 B).
5. `hop`: at each routed hop, in order: the egress interface, its `show ip interface` (`show
   ipv6 interface`), the next hop's ARP entry (its IPv6 neighbour entry), the route and what it
   is known via, the next hop's ingress interface, and a bound access list's entries. A hop
   leaving on a VLAN interface is a switch on the path: where the next hop's MAC is learned in
   that VLAN, and that port's spanning-tree state. The run stops at the first hop that diverges
   from intent, and names the hops it did not check.
6. `read again`: each hop's egress interface a second time, 10 s later.
7. `traceroute`: when the path leaves the network toward an address no managed device holds.
8. `return`: from B's device back to A, when the forward path holds and B is managed, each of
   its hops checked as a forward hop is.
9. `logs`: each device read: its configuration lines in the last hour, from Loki.
10. `compare`, `rank` and `record`: as for an adjacency, with this runbook's rules (a hop down,
    protocol down, errors rising, the next hop unresolved, the next hop's MAC not learned or its
    port not forwarding, a route known via what intent does not configure on that device, no
    route, a loop, the path leaving the network, no return path, an access list intent does not
    hold, a configuration change). At 70 commands it stops and says where: about nine hops.

Some devices do not have a read the runbook sends: an IOS switch refuses the bounded
traceroute and `show ipv6 neighbors <address>`. The step then says the device has no such read,
and a rule that needed it says its evidence is incomplete.

## The steps: a telemetry stream lost {#stream}

A telemetry stream runs from the device to its collector, on the port the subscription's
receiver names in intent. So this runbook reads that path, from both of its ends, and not a
path between two devices. Self-healing runs it when a lost-stream alert raised the incident
(see [When self-healing runs it by itself](#automatic)).

1. `plan`: the device, its lost subscriptions, and each subscription's receiver address and
   port from intent. A subscription intent does not declare is named and not read. A receiver
   with no address and port in intent has no collector to read, said.
2. `hold`: the device is held for this diagnosis.
3. `read`: on the device, through the reads engine: `show telemetry ietf subscription all`
   (each subscription's state), `show telemetry ietf subscription <id> receiver` for each lost
   subscription, and a ping to each collector address (`ping ipv6` for an IPv6 one). The
   receiver's answer is read: its State and its connection, as the device prints them, are
   evidence in the half-open and no-session hypotheses. An answer that cannot be read as a
   receiver's says so, and a hypothesis that needed it says its evidence is incomplete. A
   receiver reading Connected is not proof of a stream: a stuck device reads Connected too.
4. `collector`: when the collector is Mercury's own host, its TCP sockets on the stream's port,
   read from the kernel's tables on the host, IPv4 and IPv6: whether anything listens there,
   each session from one of the device's addresses and its state, and how many sessions stand
   from other devices; and from the kernel's socket diagnostics, each session's bytes received
   and how long since it last received anything. A session that received data within the
   stream's window (90 s) is carrying data, never half-open. Nothing is sent and nothing is
   changed. A collector at an address that is not Mercury's host is not read, and the result
   says so.
5. `stream`: each lost subscription's own series in Prometheus, by the lost-stream alert's own
   query. A series there now means the stream is back: the result says so, every cause rule is
   left unchecked (there is nothing left to explain), and self-healing reads the symptom as
   gone. Prometheus not answering decides nothing, and is said.
6. `cause`: from self-healing's own records, the change on another device just before the
   stream was lost (the one the alert names, or the only one), and whether Mercury has read
   that device back at intent since, and when.
7. `logs`: the device's configuration lines in the last hour, from Loki.
8. `compare`, `rank` and `record`: as for an adjacency, with this runbook's rules: the stream
   back in Prometheus; Mercury
   cannot read the device either; a subscription missing on the device, or not Valid; the
   device not reaching its collector; nothing listening on the collector's port; a half-open
   session (the collector still holds a session from the device while its stream is lost); no
   session from the device though the collector listens; the stream still lost well after its
   cause was put back; the cause put back too recently for the alert to have cleared; the
   cause still standing; a configuration change on the device.

**A stream that outlived its cause is a different problem from a stale one.** When the change
that broke the stream was put back longer ago than the lost-stream alert takes to clear (its
window and its evaluation interval, about 150 s), and the stream is still lost, the result
leads with that: "edge2's telemetry hasn't recovered since edge1 was put back at 20:05 UTC, 40
minutes before this diagnosis". The stream is then stuck at the device or the collector, not waiting on
the path. When it was put back less than that ago, the stream may already be back and the
alert not yet cleared: the result says so, and when to diagnose again.

What to do about a stuck stream is said with it: re-subscribe it, from the lost stream's row on
Needs attention ([Re-subscribe a lost telemetry stream](telemetry-resubscribe)), which removes
each lost subscription's receiver, waits about 10 s, adds it back and checks the stream. The
diagnosis itself changes nothing.

That row draws this diagnosis too, above Re-subscribe: its first hypothesis in plain words,
when it was read and what it says to do next
([A lost telemetry stream, opened](needs-attention#a-lost-telemetry-stream)). It draws only
one recorded since the stream was lost; with none, it says so.

## The result

The diagnosis is drawn in the card's place when the run ends: its headline (how many
hypotheses, the first one's strength), each hypothesis with its layer, strength, evidence and
what would rule it out, each piece of evidence a link to its read's run on History › Reads
(the masked answer), what was ruled out, what was not checked and why, and every step. With no
rule firing it reads "no cause found in what Mercury reads", then the ruled-out list. It never
guesses. **Run again…** opens the card again.

For "can't reach", **The path, hop by hop** comes first: the ping (how many probes were
answered; "A reaches B" when all were), each hop checked with what was read and "as intent" or
"diverges here", and the devices after the hop that diverges "not read". The
headline then names the hop ("diverges at edge2").

**Open in History** opens the device's History tab on the kind Diagnoses and the day it ran:
each diagnosis a person ran is a row there, and on History, on every device it read. A
diagnosis self-healing runs for an incident is that incident's, on its row. Leave the page
while it runs, and the device's page opens the card again when you come back, until you have
seen its result; the top bar's In progress lists it meanwhile.

"Diagnosed" is not a fix: a diagnosis on demand acts on nothing and clears nothing.

## When self-healing runs it by itself {#automatic}

Self-healing runs the same runbooks itself, once per incident, on two kinds of incident:

- **Alert:** an incident it cannot fix with the configuration at intent (an interface down
  while administratively up, or a symptom with no cause in the configuration). The diagnosis
  runs before the team is told, and the notice waits for it up to 150 s. The email and the
  webhook carry it after what was detected, by kind only: each hypothesis's rule, the ends or
  hops it read and its strength, and what was ruled out, never a value it compared or a
  configuration line. If it has not finished by then, the notice says so and a follow-up on
  the same thread carries it. Its AI analysis, when that is on, reads it too, by kind.
- **Propose:** a fix that waits for a person. The diagnosis runs once the fix is proposed, and
  the proposal's card draws it beside Approve and Decline, so the person approving sees what
  Mercury read. When its first hypothesis is decisive and is a physical or link fault, the card
  says the fix does not change it. A diagnosis never withdraws a proposal.

It chooses the runbook from what raised the incident: a lost telemetry stream runs "a
telemetry stream lost" on the device, whatever else raised it too (when Mercury cannot read the
device either, that is its first hypothesis, pointing at Can't reach); an alert that the device
is unreachable runs "can't reach" toward the device's loopback from its first neighbour by
intent; an alert
naming an interface, or an adjacency down, runs "an adjacency is down" on that adjacency, and
only on it. A named interface that intent holds no adjacency over is not diagnosed, and the row
says so: no other link is read in its place.

At most 3 run at once on a network. A fourth says "not diagnosed: 3 diagnoses already running"
on its row, and **Diagnose…** there runs one. Each is recorded on its incident's row (Needs
attention, under "Mercury's diagnosis") and on the History of every device it read. A Never
incident (a security ACL, a change to Mercury's path) is not diagnosed by itself: Diagnose… on
its row runs one.

## What it never does

It sends no configuration command, no `clear counters`, no `send log` and no `terminal`
setting: every command passes the reads engine's read-only allowlist with nothing added. It
calls no AI model. It reads no device that is not part of the adjacency or the path. On
Mercury's host it only reads the kernel's socket and address tables, for a lost stream's
collector.
