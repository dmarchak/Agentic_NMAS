# A flow-table trace: a packet through an SDN fabric

Topology's **Path…**, on the **Flow tables (OpenFlow)** layer, answers "where does a packet from
this host to that host go through the switches a controller programs?" from the flow tables the
controller last reported: each switch's datapath ID (DPID), the port the packet comes in by, the
flow that decides it, and the port it leaves by. It reads what the SDN reader stored; it asks
nothing of the controller or any switch, sends no traffic and changes nothing, so any viewer may
trace and nothing is recorded.

![A flow-table trace: an end given by name is looked up among NetBox's end hosts in the network's committed NSOT export and traced by its MAC; the SDN reader's stored read is read once; each end is found among the hosts the controller lists, or refused with nothing asked; the packet is built, ICMP echo or TCP or UDP to a port, in the addresses' family; it is walked through each switch's flow tables by OpenFlow 1.3.5's rules, switch to switch along the links the controller reports; each branch ends in one named outcome, and Topology draws the switches with their DPIDs and ports. Nothing is asked of the controller or any switch.](diagrams/sdn-trace.svg)

## The steps

1. `name`: **From** and **to** each take an IPv4 or IPv6 address or a MAC, as the controller
   lists its hosts, or an end host's name as NetBox records it. A name is looked up among the
   end hosts in the network's committed NSOT export (devices tagged `mercury-end-host`; see
   [Commit a network's NSOT export](nsot-export)) and traced by its interface's MAC; the answer
   says so, naming the export. A name the export does not record, an export built before end
   hosts were recorded, or no committed export, is refused, saying which. An address or a MAC
   is never looked up there.
2. `read`: the SDN reader's stored value is read once: per controller its switches with their
   ports, the links it discovered, the hosts it learned, and each switch's whole flow table.
   Nothing is read per switch while you look.
3. `find`: each end is found among the hosts the controller lists on an edge port (a port with
   no link to another switch). An address no controller lists is refused, naming it and how many
   hosts are listed; one listed at two places is refused naming both, because the controller
   keeps a host until it restarts, and each place's MAC is offered as a trace. The two ends must
   be on one controller's fabric.
4. `packet`: the packet a host sends: an ICMP echo (ICMPv6 for IPv6), or TCP or UDP from port
   49152 to the port given, untagged. Its family is the one the addresses given name; two MACs
   take IPv4 where both hosts have an IPv4 address, else IPv6, and the answer names it. Its
   MACs are the controller's host table's, as if ARP or neighbour discovery had already
   resolved them. A port is from 1 to 65535; ICMP has none, so Port is off for it.
5. `walk`: from the source's port, each switch's pipeline runs as OpenFlow 1.3.5 says: table 0
   first and forward only, the highest-priority flow that matches in each table, its
   instructions in order, then the action set, output last. The packet leaves by each port it
   is output to and arrives at the switch the controller lists a link to, until it ends.
   A flood leaves by every listed port but the one it came in by, each a branch.
6. `answer`: each branch ends in one outcome, with the flow that decided it: **delivered** (the
   destination's port; green), **dropped** (by a flow with no output, by no flow matching with
   no table-miss entry, or by a port that is not there), **to another host**, **a loop**,
   **to the controller** (its table-miss entry, for a controller that installs flows when a
   packet arrives), **leaves the fabric** (a port with no link and no host listed; grey),
   **to the switch itself**, or **cannot tell** (amber), naming why: a group, NORMAL, a VLAN,
   MPLS or PBB push or pop, a field the trace does not build, two flows at one priority with
   different actions, or a switch whose table was not read. Past 256 branches the rest are
   counted, never drawn.

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
