# A flow-table trace: a packet through an SDN fabric

Topology's **Path…**, on the **Flow tables (OpenFlow)** layer, answers "where does a packet from
this host to that host, or to that address, go through the switches a controller programs?"
from the flow tables the controller last reported: each switch's datapath ID (DPID), the port
the packet comes in by, the flow that decides it, and the port it leaves by. It reads what the
SDN reader stored; it asks nothing of the controller or any switch, sends no traffic and
changes nothing, so any viewer may trace and nothing is recorded.

![A flow-table trace: NetBox's names are read once from the network's committed NSOT export, for the hosts From offers and for an end given by name; the SDN reader's stored read is read once; each end is found among the hosts the controller lists, by address, by MAC or by its NetBox interface's MAC, or refused with nothing asked, and a destination that is only an address is followed too; the packet is built, ICMP echo or TCP or UDP to a port, in the addresses' family; it is walked through each switch's flow tables by OpenFlow 1.3.5's rules, switch to switch along the links the controller reports; each branch ends in one named outcome, and Topology draws the switches with their DPIDs and ports. Nothing is asked of the controller or any switch.](diagrams/sdn-trace.svg)

## From and to

**From** is a choice, never typed: the hosts Mercury knows. Each is a host the controller
lists on an edge port, named from NetBox where NetBox names it (the NetBox name first, then
its MAC, then its address; a host NetBox does not name is shown by its switch and port), or a
host NetBox cables to a switch port that the controller has not learnt, said as such. Nothing
is chosen until a person chooses.

**to** is a box that takes one of the same hosts (its first twenty are suggested as the box
is typed in) or anything typed: an IPv4 or IPv6 address, a MAC, or a NetBox name. An address
that no controller lists and no NetBox interface holds is not refused: the packet is followed
to that address (see "A destination that is only an address"). Anything else that is no host
is refused, naming what it was compared with.

## The steps

1. `name`: NetBox's view of the fabric is read once, from the network's committed NSOT export
   (see [Commit a network's NSOT export](nsot-export)): each switch's name by its datapath id
   (the device's `openflow_datapath_id`), and every interface of an end host (a device tagged
   `mercury-end-host`) or of a device that is not a switch, with its MAC, its addresses and
   the switch port its cable ends on. It names From's choices, and it answers an end given by
   NAME or by an address only NetBox records. The form says which export the names are from;
   a network with no committed export, or one that cannot be read, says so, each in its own
   words, and offers the controller's hosts by switch and port.
2. `read`: the SDN reader's stored value is read once: per controller its switches with their
   ports, the links it discovered, the hosts it learned, and each switch's whole flow table.
   Nothing is read per switch while you look.
3. `find`: each end is found among the hosts the controller lists on an edge port (a port with
   no link to another switch), by its address or MAC. A NetBox name, or an address only NetBox
   records, is the host the controller lists with that interface's MAC; where NetBox records
   no MAC, the one host listed on the port its cable ends on; and where the controller has
   learnt no such host, NetBox's own place for it (the switch's datapath id and the port's
   OpenFlow number), with NetBox's MAC and addresses. The answer says which source answered.
   One listed at two places is refused naming both, because the controller keeps a host until
   it restarts, and each place's MAC is offered as a trace; a name with two interfaces a
   controller lists is refused the same way. A From that is no host Mercury knows is refused,
   naming it and how many hosts are listed. The two ends must be on one controller's fabric.
4. `packet`: the packet a host sends: an ICMP echo (ICMPv6 for IPv6), or TCP or UDP from port
   49152 to the port given, untagged. Its family is the one the addresses given name; two MACs
   take IPv4 where both hosts have an IPv4 address, else IPv6, and the answer names it. Its
   MACs are the controller's host table's (NetBox's for a host it has not learnt), as if ARP
   or neighbour discovery had already resolved them. A port is from 1 to 65535; ICMP has none,
   so Port is off for it.
5. `walk`: from the source's port, each switch's pipeline runs as OpenFlow 1.3.5 says: table 0
   first and forward only, the highest-priority flow that matches in each table, its
   instructions in order, then the action set, output last. The packet leaves by each port it
   is output to and arrives at the switch the controller lists a link to, until it ends.
   A flood leaves by every listed port but the one it came in by, each a branch.
6. `answer`: each branch ends in one outcome, with the flow that decided it: **delivered** (the
   destination's port; green), **dropped by a flow** (a flow with no output, named by its
   priority, table, cookie and id; red), **table-miss: dropped** (no flow matched and the
   table has no table-miss entry, or its table-miss entry has no output; red), **dropped** (a
   port that is not there, or back out the port it came in by), **to another host**, **a
   loop**, **table-miss: to the controller** (no flow matched and the table-miss entry sends
   it to the controller, as a controller that installs flows when a packet arrives does;
   amber), **to the controller** (a flow that outputs there by name), **leaves the fabric** (a
   port with no link and no host listed, named; grey), **to a listed host** (an address-only
   destination whose packet reaches a host's port; grey), **to the switch itself**, or
   **cannot tell** (amber), naming why: a group, NORMAL, a VLAN, MPLS or PBB push or pop, a
   field the trace does not build, two flows at one priority with different actions, or a
   switch whose table was not read. Past 256 branches the rest are counted, never drawn.

## A destination that is only an address

A to that is an address nothing lists (an address nothing answers, or one beyond the fabric)
is followed from the From host, with that destination address, until it ends: a flow drops
it, the table-miss takes it (to the controller, or dropped, as the table says), it leaves by
a port with nothing listed behind it, or it reaches a listed host's port. No port is that
address's own, so the answer never says delivered and never says "not delivered": it leads
with how the packet ended.

Nobody knows that address's MAC, so the answer says what the packet assumes: its destination
MAC is `00:00:00:00:00:00`, the "not known" value an ARP request itself carries, which a flow
that names a destination MAC does not take. A real host would first ask for the address (ARP,
or IPv6 neighbour discovery), and would send a packet for an address beyond its gateway to
the gateway's MAC; neither is traced. So a drop or a table-miss on the From host's own switch
is shown as it is; a flow further along a path that forwards by destination MAC is not
reached, because the first switch's flows for a known MAC do not take this packet. There is
no **Trace the reverse** from an address nothing lists: a trace starts at a host.

## The answer

The card leads with the answer (delivered through how many switches, or where and how it ended)
and its chip, then the switches in order, each its DPID with the port it came in by and the port
it left by, both named: the lab's question in one line. Below, the hops table: each switch (its
link opens its flows on SDN › Flows), the flow that decided it (table, priority, cookie, match
and instructions) and its owner, and where the packet went next; open a hop's flow to see every
flow its pipeline ran, in order. **The packet traced** shows the exact fields walked. A trace
with several branches leads with a summary by ending; the delivered branch is drawn, the others
grouped by ending and closed; a branch longer than six switches folds its middle.

**Trace the reverse** swaps From and to: each direction is its own flows in OpenFlow, so the
way back is a second question, never assumed. **Copy the hops** copies the answer's one line,
the DPIDs with their in and out ports. **Clear the path** takes the card and the map's
highlight away. Layer, From, to, Protocol and Port are in the page's address, so a trace is a
link anyone can open. On the map the path is drawn on, each switch on it ringed; a branch that
stops short is drawn red to the switch where it stops.

## A stale read

The answer is where the packet went through the tables as they were last read. When the
controller has not been read within its promise, the answer says "as last read", loses its
colour, and a notice says since when and why; the switches may hold other flows now. The card
redraws by itself as each new read arrives, so there is no Trace again.

## What it does not trace

ARP and IPv6 neighbour discovery; a TTL running out (a flow that changes the TTL, or sends the
packet through a meter, is noted on the way and not modelled); a packet the controller handles
(the trace stops where a switch sends it to the controller); and the routed layer beyond the
fabric: a path leaving the fabric toward a router ends "leaves the fabric", and the Routing
(CEF) layer is [A path trace](path-trace). The trace is checked on Open vSwitch's tables under
Ryu; another switch's table may spell a match or action it does not model, which it says as
"cannot tell", never a wrong path.
