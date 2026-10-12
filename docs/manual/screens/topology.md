# Topology

How each network is connected, what each link carries and how it compares with committed intent,
and where the network is weak. The page names its network (`/v2/topology?list=<network>`) and
draws what the topology reader last read from Prometheus: LLDP's neighbour tables, the OSPF,
OSPFv3 and BGP neighbour tables, and each interface's state and speed, against each device's
committed intent. RIP and RIPng have no neighbour table Prometheus holds, so a second reader asks
the devices whose intent configures them, every five minutes, two read-only show commands each
(`show ip protocols` for the gateways RIP hears, `show ipv6 rip next-hops` for RIPng's). The page
never reads a device while you look; the header says how old the read is, and the page redraws
by itself when a reader reads something new.

## The map {#map}

One physical map. Each device is drawn as its class's icon (a switch that runs a routing protocol
is badged **L3**; a peer outside management is a cloud with its AS; Mercury's own host is drawn
where it attaches). Each device opens its page. The map has no bands: devices sit where the
network's shared layout puts them (see [Arranging the map](#arrange)), and where nobody has placed
them, where the cabling's springs settle them, from a fixed seed. A refresh moves nothing.

Every link is labelled:

- **the port at each end** (r1 Gi2 ↔ s3 Gi1/0), LLDP's own names;
- **a chip for each routing protocol between its two ends**, in two words: the protocol and the
  state (`OSPF FULL`, `OSPFv3 FULL`, `BGP Estab`, `OSPF 2WAY`). BGP's IPv4 and IPv6 sessions to one
  peer in the same state are one chip. The area and the peer's AS are in the link's card.
- RIP and RIPng are chipped the same way: `RIP up` when both ends hear each other, `RIP one-way`
  when one end hears the other and the other, read, hears nothing, `RIP up?` when the other end
  could not be read. Intent says where RIP runs (an interface in a `network` statement, in the
  global table, not passive) and where RIPng is enabled; the subnet is in the link's card. When
  the RIP reader's answer is missing or older than its promise, intended RIP and RIPng are
  chipped `RIP ?` and `RIPng ?`: not read, never drawn as up and never as missing.

A link that carries a switched segment (VLAN 100's trunks) also carries neighbourships between
OTHER devices on that segment. Those get no chip while they are as intended; one that is not gets
its own, naming both devices (`OSPF r1–r3 2WAY`). The card lists every one passing over the link.
A neighbourship no link carries (between loopbacks) is drawn thin, straight between the two
devices.

2WAY is what OSPF intends between two devices on a segment where neither is the DR or BDR. The
DR and BDR are worked out from the neighbourships themselves (the devices FULL with most of the
segment). A 2WAY anywhere else, or any other state short of FULL, is **not as intended**:
"2WAY, intended FULL".

The line says how the link compares with intent, never by colour alone:

- **green, solid**: as intended;
- **orange, dashed**: up, not as intended: only one end's LLDP reports it while both are polled
  and nothing else confirms it, a neighbour committed intent does not name, an OSPF neighbour
  short of FULL where FULL is intended, or RIP heard one way;
- **red, thick**: down, or a neighbour intent names that nothing reports;
- **grey, dotted**: not read.

**A link is drawn as intended only when two witnesses agree it is there.** Both ends' LLDP is
two. When only one end's LLDP reports it and the other end is polled and reports no neighbour on
that port, the second witness is a routing adjacency both ends report on the link's own ports
(OSPF, OSPFv3 or BGP up, or RIP or RIPng heard both ways). With one, the link is green and its
card's **LLDP** row still says which end is silent, with what was measured; without one, the
line is orange and Needs attention lists it. Neither case is explained by the device's platform:
the card says what was read, never why a device might not send or hear LLDP.

**Hover** on a link (or tab to it) for its card: both ends, the link's state and since when, a
row per protocol with its area or the peer's AS, the state against intent ("2WAY, intended FULL;
since 20:58 UTC"), what passes over the link, and links to each end's Neighbours tab. **Click** a link
to select it (or click its entry in Needs attention): it glows, its card stays open, and its
entry is marked. To close it, click the card's **×**, click anywhere on the map's empty space, or
press **Escape**.

The toolbar: **Protocols** chooses which protocols' chips and states are drawn (OSPF, OSPFv3, BGP,
RIP / RIPng; EIGRP and IS-IS are drawn unpressed and do not press, since Mercury does not read
them); **Ports** shows or hides the port names (on at the desktop, off at phone width); **Labels**
Auto shows ports and chips at 100% and closer and hides them zoomed out, On always, Off never;
**Reset layout** (see below); **−, 100%, +** zoom about the middle, 100% fitting the whole map;
**Weak points** tags single points of failure and islands on the map. **Find** rings a device
whose name, role, address or port matches; it never hides anything.

## Arranging the map {#arrange}

The map fills the window; a large network does not fit on one screen, so you move around it:

- **Drag empty space** (or a link) to pan.
- **The mouse wheel**, or a pinch on a trackpad or a phone, zooms in and out **at the pointer**.
  How far you are zoomed is the middle button's percentage; Labels Auto hides ports and chips
  while you are zoomed out.
- **Drag a device** to move it, with a mouse or a pen on a wide screen (with the keyboard: focus
  a device and press **Alt** and an arrow, **Shift** for a longer step). When you let go, the map
  as it then stands is saved as **this network's layout, for everyone**: the device is faded until
  the save answers, and the line under the map says who arranged it and when. Each move is
  recorded on History (Topology layouts), with your name and the device; a device's own History
  lists its moves. At phone width you pan and zoom; devices are moved on a wider screen.
- A device added since the layout was saved is **placed near its neighbours**; no device anyone
  placed moves.
- **Reset layout** withdraws every person's moves: the map is laid out by the cabling again, for
  everyone, and the reset is recorded on History. It is greyed out while nobody has moved a
  device.

Moving a device changes nothing on any device or in any record but the layout: it is where the
device is drawn, nothing more.

## Needs attention on the map {#attention}

Every link that is not as intended, grouped by its line style (down or a neighbour missing; up,
not as intended; not read), each saying what is wrong and since when ("at least since" when the
state was already so at the reader's first read); then the **weak points**. The counts lead and
are always the whole; a group button or the filter shows a part, and says so. Click an entry to
select its link on the map.

## A path {#path}

**Path…** traces the path packets take from a device to an address, read from each routed hop's
own forwarding table, never worked out from the cabling. **From** offers the devices that take
part in routing; **To** offers each outside peer's peering addresses (an ISP's router, by the
address each of your edge routers peers with) and each routing device's loopback. **Trace the
path** reads the first device, follows the next hop its answer names to the device holding
that address, and reads that one, until the packet is delivered or the trace stops; the button
says which devices it is reading until the answer arrives. How it works:
[A path trace](path-trace).

The card names each branch (equal-cost next hops split traffic per flow, so a trace can have
several), each hop's forwarding answer and the next hop, and how the branch ends: delivered,
dropped (a device with no route), not read (a device that did not answer or another operation
holds; what follows is not known, never guessed), a loop, leaving the network (a next hop no
device of the network holds), or a bound (more than 8 branches or 16 hops). On the map a
delivered branch is drawn on, one that is not in red to where it stops; the switches between two
routed hops are dashed, since a trace reads layer 3 only. Every read is on History › Reads.
**Clear the path** takes it off the map; **Trace again** reads it afresh.

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
bridge.

## At phone width {#phone}

Three tabs: **Attention** (first: the counts, then each group's links as a list), **Devices**
(every device grouped by kind, routers, switches and the rest, with its ports and links; on the
desktop this list appears only for a fleet too large to draw) and **Map**, where you pan with a
finger and pinch to zoom. Ports are off by default; **Ports** and **Labels** are
under the tabs. A selected
link opens as a sheet at the bottom, with its ends, each protocol's state, the first end's
Neighbours and **Show on the map**.

## What it cannot see {#limits}

A link with no LLDP (a device with LLDP off, or through a bridge that drops it), shared conduits
and power, anything outside management, and the protocols Mercury does not read. A
neighbourship's state is the Neighbours tab's comparison: what each device reports, against
what its committed intent implies.
