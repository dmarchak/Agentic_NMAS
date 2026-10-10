# Topology

How each network is connected, what depends on what, and where it is weak. The page names its
network (`/v2/topology?list=<network>`) and draws what the topology reader last read from
Prometheus: LLDP's neighbour tables, the OSPF, OSPFv3 and BGP neighbour tables, and each
interface's state and speed. It never reads a device while you look; the time of the read is
beside the question, and the map redraws by itself when the reader reads something new.

## The question {#question}

- **Layer**: Physical (LLDP), OSPF, OSPFv3 or BGP. Under a routing layer the physical links stay
  drawn faintly, so an adjacency with no cable beneath it, or a cable with no adjacency, shows.
- **Path from … to …**: every shortest path between the two devices in the chosen layer's graph,
  by hop count, each hop with its ports. It is a claim about the GRAPH, never about forwarding:
  what a packet takes is the routing table's.
- **Find**: a device, a role or a port. What matches is ringed on the map; nothing is hidden.

The counts come first: devices, outside peers, links by state, islands to look at, expected
islands, single points of failure.

## The map {#map}

Devices sit in bands by role, top to bottom; peers outside management above them; islands in a
band of their own below. A refresh moves nothing. Each device opens its page.

A link is the union of what both ends report:

- **solid**: up, reported by both ends;
- **dotted**: reported by one end only, either because the far end is not polled (normal) or
  because both are polled and one is silent;
- **dashed and crossed**: down at one end at least (hover names the end);
- **faint dashed**: a routing adjacency committed intent implies that nothing reports.

A crossed circle is a device not answering; a ringed one with **SPOF** is a single point of
failure; a grey dashed circle is outside management. Down is never colour alone. Hover on any
link or device for its detail (ports, speed, who reports it). Below 700 px the list by band is
shown first and **Show the map** opens the map.

## Outside peers {#outside}

A device the fleet peers with and does not manage (an ISP's router, a decommissioned device
still in service) is drawn once, outside the fleet: never a fleet device, never an island. A
routing peer known only by its address is named through the LLDP neighbour on the interface
whose subnet holds that address; otherwise it is drawn by its address.

## Islands {#islands}

An island is a part of the fleet no link joins to the rest, each with why (not polled, no LLDP
neighbour, connected only among themselves). In a routing layer it is among the devices running
that protocol.

An island cabled apart **on purpose** (a device on its own management segment, say) can be
marked: **Mark as expected…** asks why; it needs a verified person and is recorded on History
(Expected islands), with your name. The map then draws it as expected, with the reason, and
warns nothing. **Withdraw** puts the warning back. A device that **becomes** an island (one
that was not an island at the last read) is told apart: "became an island", with when.

## Single points of failure {#spof}

A device whose loss splits the graph (an articulation point), or a link whose loss does (a
bridge), each with what it would cut off. Parallel links are never a bridge. Below, the devices
most traffic must pass through (betweenness).

## What it cannot see {#limits}

A link with no LLDP (a device with LLDP off, or through a bridge that drops it), shared conduits
and power, and anything outside management. A routing layer is the Neighbours tab's comparison:
what each device reports, against what its committed intent implies.
