# Topology

How each network is connected, what each link carries and how it compares with committed intent,
and where the network is weak. The page names its network (`/v2/topology?list=<network>`) and
draws what the topology reader last read from Prometheus: LLDP's neighbour tables, the OSPF,
OSPFv3 and BGP neighbour tables, and each interface's state and speed, against each device's
committed intent. It never reads a device while you look; the header says how old the read is,
and the page redraws by itself when the reader reads something new.

## The map {#map}

One physical map: each device as its class's icon (a switch that runs a routing protocol is
badged **L3**), each peer outside management as a cloud with its AS, and Mercury's own host
where it attaches. Each device opens its page. The map first draws a generated layout, routers
above switches; **Arrange** lets you put every device where you want it, for everyone (below).

At Fit the map shows devices, links and their state, by line style and colour, with the legend:

- **green, solid**: as intended;
- **orange, dashed**: up, not as intended: only one end reports it while both are polled, a
  neighbour committed intent does not name, or the two ends of a neighbourship disagree;
- **red, thick**: down, or a neighbour intent names that nothing reports;
- **grey, dotted**: not read.

**Labels**: with Labels **Auto**, a link's labels show when you hover on it, tab to it or select
it, and every link's labels show at 150% and closer; **On**, always; **Off**, never. A link's
labels are:

- **the port at each end** (r1 Gi2 ↔ s3 Gi1/0), LLDP's own names;
- **one chip per neighbourship**, with its key fact and state: OSPF and OSPFv3 with their
  **area** (`OSPF area 0: FULL`), BGP with the **peer's AS** and whether it is eBGP or iBGP
  (`eBGP AS 65002: Estab (IPv4, IPv6)`, two sessions in the same state). Both ends' reports are
  one chip; when they disagree, both are named and the chip is flagged
  (`OSPF area 0: r3 FULL / r4 2WAY (ends disagree)`).

A protocol Mercury does not read (RIPng, EIGRP, IS-IS) adds no label: a link's card says where
committed intent configures it.

## Multi-access segments {#segments}

A subnet where OSPF or OSPFv3 joins more than two devices (a VLAN shared by routers and L3
switches) is drawn as **one segment node**, named by its VLAN, with each member joined to it by
a thin line. Its OSPF and OSPFv3 summary is on the segment, once: how many devices, and which
are the **DR and BDR** (the devices FULL with the most others; a DROther is FULL with the DR and
BDR only). **2WAY between two DROthers is how OSPF works, never a fault.** What is flagged: an
adjacency down or missing, a 2WAY with the DR or BDR (expected FULL), the two ends disagreeing,
and no device standing out as DR and BDR. Hover on the segment for every member's neighbours.

**Hover** on a link (or tab to it) for its card: both ends, the link's state and since when, each
neighbourship with its state, and links to each end's Neighbours tab. **Click** a link or a
segment to select it: it glows, its labels and card stay shown, and its entry in Needs attention
is marked.

The toolbar: **Protocols** chooses which protocols' labels and states are drawn; **Ports** shows
or hides the port names (on at the desktop, off at phone width); **Labels** as above; **−, Fit,
+** zoom; **Weak points** tags single points of failure and islands; **Arrange** (below).
**Find** rings a device whose name, role, address or port matches; it never hides anything.

## Arrange {#arrange}

**Arrange** lets you design the map: drag a device or a segment where you want it (or tab to it
and use the arrow keys: 10 at a time, 50 with Shift), then **Save the layout**. The layout is the
network's, the same for everyone, and recorded on History (Topology layouts) with your name. A
device added later takes its generated place until you arrange it. **Cancel** drops what you
moved; **Reset to the generated layout** withdraws the saved one for everyone. While you
arrange, the map holds still: a change the reader brings waits until you save or cancel.
## Needs attention on the map {#attention}

Every link that is not as intended, grouped by its line style (down or a neighbour missing; up,
not as intended; not read), each saying what is wrong and since when ("at least since" when the
state was already so at the reader's first read); then the **weak points**. The counts lead and
are always the whole; a group button or the filter shows a part, and says so. Click an entry to
select its link on the map.

## A path {#path}

**Path…** asks for two devices and draws every equal-cost shortest path between them over the
physical links that are up, each hop with its ports. It is a claim about the graph, never about
forwarding: what a packet takes is the routing table's. A path across islands says why there is
none.

## Take out a device (what-if) {#what-if}

**Take out a device…** works out, on the stored map, what losing one device would cut off: the
devices that would lose the rest, or that Mercury itself would lose every device when the device
is its only way in. Those devices are marked "cut off" on the map. Nothing is sent to a device;
**Put it back** clears it.

## Outside peers {#outside}

A device the fleet peers with and does not manage (an ISP's router, a decommissioned device
still in service) is drawn once, as a cloud with its AS: never a fleet device, never an island.
A routing peer known only by its address is named through the LLDP neighbour on the interface
whose subnet holds that address; otherwise it is drawn by its address.

## Mercury's own host {#mercury}

Mercury's host is drawn where it attaches, measured, never declared: the device interface whose
subnet holds one of this host's own addresses. For a VLAN interface, the port is the one port
carrying that VLAN with no device beyond it. When that device is Mercury's only way in, it is a
**single point of failure**, and the weak point says so. A host attached nowhere a device's
intent can see is not drawn.

## Islands {#islands}

An island is a part of the fleet no link joins to the rest, each with why (not polled, no LLDP
neighbour, connected only among themselves), tagged on the map and listed under weak points.

An island cabled apart **on purpose** (a device on its own management segment, say) can be
marked: **Mark as expected…** asks why; it needs a verified person and is recorded on History
(Expected islands), with your name. It then moves to **Apart on purpose**, with the reason, and
warns nothing. **Withdraw** puts the warning back. A device that **becomes** an island (one that
was not an island at the last read) is told apart: "became an island", with when.

## Single points of failure {#spof}

A device whose loss splits the network (an articulation point), or a link whose loss does (a
bridge), each with what it would cut off, among the weak points. Parallel links are never a
bridge. Below them, the devices most paths pass through (betweenness).

## At phone width {#phone}

Three tabs: **Attention** (first), **Devices** (every device by band, with its ports and links)
and **Map**. Ports are off by default; **Ports** and **Labels** are under the tabs. A selected
link opens as a sheet at the bottom, with its ends, each protocol's state, the first end's
Neighbours and **Show on the map**.

## What it cannot see {#limits}

A link with no LLDP (a device with LLDP off, or through a bridge that drops it), shared conduits
and power, anything outside management, and the protocols Mercury does not read. A
neighbourship's state is the Neighbours tab's comparison: what each device reports, against
what its committed intent implies.
