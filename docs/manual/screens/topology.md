# Topology

How each network is connected, what each link carries and how it compares with committed intent,
and where the network is weak. The page names its network (`/v2/topology?list=<network>`) and
draws what the topology reader last read from Prometheus: LLDP's neighbour tables, the OSPF,
OSPFv3 and BGP neighbour tables, and each interface's state and speed, against each device's
committed intent. RIP and RIPng have no neighbour table Prometheus holds, so a second reader asks
the devices whose intent configures them, every five minutes, two read-only show commands each
(`show ip protocols` for the gateways RIP hears, `show ipv6 rip next-hops` for RIPng's). The page
never reads a device while you look; the header says how old the read is, and the page redraws
by itself when a reader reads something new. Until the topology reader has read, when its store
cannot be read, when Prometheus is not configured, or when the network was not in its last read,
the page says which and draws no map; when its last read failed, it draws the last good read and
says when it was.

An interface's address is its static one in committed intent. An interface that says
`ip address dhcp` on a device onboarded with a DHCP or ZTP address has the address its lease
gave it, recorded by onboarding's Verify (the committed manifest), so the OSPF and RIP it runs
there are intended like any other. Only IPv4 is leased this way (DHCPv6 is not supported); a
device with several `dhcp` interfaces outside a VRF is not guessed, and none of them has an
address here.

## The map {#map}

One physical map. Each device is drawn as its class's icon (a switch that runs a routing protocol
is badged **L3**; a peer outside management is a cloud with its AS; Mercury's own host is drawn
where it attaches). Each device opens its page. The map has no bands: devices sit where the
network's shared layout puts them (see [Arranging the map](#arrange)), and where nobody has placed
them, where the cabling's springs settle them, from a fixed seed. A refresh moves nothing.

Every link is labelled:

- **the port at each end** (edge1 Gi2 ↔ core1 Gi1/0), LLDP's own names;
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
its own, naming both devices (`OSPF edge1–edge2 2WAY`). The card lists every one passing over the link.
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
**Snap to grid** and **Reset layout** (see below); **−, 100%, +** zoom about the middle, 100%
fitting the whole map;
**Weak points** tags single points of failure and islands on the map (on unless you turn it off).
**Find** rings a device whose name, role or port contains what you typed, or one of whose
addresses is exactly it; it never hides anything.

Above 150 devices the map is not drawn whole: Needs attention names every link to review,
**Devices** lists every device by kind, and Find, a path or a device's page shows one part.

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
- **Snap to grid** lines devices up evenly. While it is on, the map shows a faint dot every 40
  map units; as you drag a device, a dashed outline marks the dot nearest to it, and when you let
  go it lands there (Alt and an arrow move it one dot, Shift three). Only what you move snaps:
  turning it on moves nothing, and a layout saved before keeps every place until that device is
  moved. The switch is yours, kept in the page's address like Ports and Weak points, never in the
  network's layout; it is off until you press it.
- **While you hold the mouse button down, the map is not redrawn.** Another person's move, the
  topology reader's next read, or the answer to your previous drop waits until you let go; then
  the map shows it. What you are dragging never jumps under the pointer.
- **A drop far from the pointer is refused.** When you let go, the device lands where the pointer
  has carried it (on the nearest dot with the grid on). If the place it would be saved at is more than one
  grid step (40 map units) from there, on either axis, nothing is saved: the device goes back to
  where it was, and a notice above the map names both places. Drag it again.
- A device added since the layout was saved is **placed near its neighbours**; no device anyone
  placed moves.
- **Reset layout** withdraws every person's moves: the map is laid out by the cabling again, for
  everyone, and the reset is recorded on History. It is greyed out while nobody has moved a
  device. When the saved layout cannot be read, the map is laid out by the cabling, a move is
  refused, and Reset layout sets the unreadable layout aside under a dated name (kept).

Moving a device changes nothing on any device or in any record but the layout: it is where the
device is drawn, nothing more.

## Needs attention on the map {#attention}

Every link that is not as intended, grouped by its line style (down or a neighbour missing; up,
not as intended; not read), each saying what is wrong and since when ("at least since" when the
state was already so at the reader's first read); then the **weak points**. The counts lead and
are always the whole; a group button or the filter shows a part, and says so. Click an entry to
select its link on the map.

A routing adjacency that drops and comes back between two of the reader's reads is not on the
map, which draws what was scraped. The sidebar's Needs attention lists it all the same when a
device logged it going down outside any planned restart or deploy: one row per adjacency,
clearing a day after its last drop, or acknowledged while its daily count stays within its
measured band.

## A path {#path}

**Path…** traces the path packets take from a device to an address, read from each routed hop's
own forwarding table, never worked out from the cabling. **From** offers the devices that take
part in routing; **To** offers each outside peer's peering addresses (an ISP's router, by the
address each of your edge routers peers with) and each routing device's loopback. **Trace the
path** reads the first device, follows the next hop its answer names to the device holding
that address, and reads that one, until the packet is delivered or the trace stops; the button
says which devices it is reading until the answer arrives. It needs a verified person, and To
must be an IPv4 address: the trace reads IPv4 forwarding only. A refused trace says
**Path: not traced** with why, and nothing is asked of any device. How it works:
[A path trace](path-trace).

The card names each branch (equal-cost next hops split traffic per flow, so a trace can have
several), each hop's forwarding answer and the next hop, and how the branch ends: delivered,
dropped (a device with no route), not read (a device that did not answer or another operation
holds; what follows is not known, never guessed), a loop, leaving the network (a next hop no
device of the network holds, or a device outside it such as the ISP's router: where Mercury's
knowledge of the path ends, the right outcome for an address beyond the network), or a bound
(more than 8 branches or 16 hops). On the map a delivered branch is drawn on, one leaving the
network in grey to where it leaves, one that stops short in red to where it stops; the switches
between two routed hops are dashed, since a trace reads layer 3 only. Every read is on History › Reads.
**Clear the path** takes it off the map; **Trace again** reads it afresh. The latest 50 traces
of a network are kept; a link to an older one says it is no longer kept.

## Take out a device (what-if) {#what-if}

**Take out a device (what-if)…** works out, on the stored map, what losing one device would cut
off: choose it under Take out and press **Show what it cuts off**. The answer names the devices
that would lose the rest, or that Mercury itself would lose every device when the device is its
only way in. Those devices are marked "cut off" on the map. Nothing is sent to a device;
**Put it back** clears it.

## Outside peers {#outside}

A device the fleet peers with and does not manage (an ISP's router, a decommissioned device
still in service) is drawn once, as a cloud with its AS: never a fleet device, never an island.
A routing peer known only by its address is named through the LLDP neighbour on the interface
whose subnet holds that address; otherwise it is drawn by its address.

## From an SDN controller {#controller}

OpenFlow switches run no LLDP of their own, so a network with an SDN controller connection
(Settings › Integrations, the SDN controllers card) takes their part of the map from the
controller that discovered it. The SDN reader reads each controller's topology every 30
seconds with the rest of what it reads ([SDN](sdn#read)): its switches with their ports, the
links between them, and the hosts it learned. The topology reader draws that stored read; it
never asks a controller itself, and the endpoint layer takes the hosts from the same stored
read.

- **A switch the controller programs** is drawn with its own symbol, in the controller's
  colour, keyed by its DPID, never by its name: under the name it reports, `of:…0001 · via
  controller`. Its card on hover gives the whole DPID, the controller that discovered it, when
  it was read, and how many ports it has.
- **Each link says where it came from**: `LLDP`, `controller`, or `LLDP + controller`. On the
  map (with Labels on) as a chip on the link, in its card on hover (the **Source** row, naming
  the controller connection and each end's port name), in Needs attention and in the Devices
  list. A link the controller reports is drawn in the controller's colour while the controller
  is read; one it can no longer read stays, grey and dotted, "as last read".
- **A hybrid link**: when a device's LLDP names a neighbour by a DPID (the chassis id
  `dpid:<16 hex digits>` an OpenFlow controller's own LLDP carries), that neighbour is the
  switch with that DPID and the port its LLDP names: one link, both sources noted. The chassis
  id is read from Prometheus (`lldpRemChassisId`); an installation whose LLDP module does not
  scrape it joins no hybrid link. A DPID no controller of the network reports is drawn as that
  device's LLDP alone sees it.
- **The controller and its hosts** are drawn beside the fabric: the controller with a dotted
  control link to each switch it manages, and each host it learned with a dashed link to its
  switch port (up to 64 hosts; above that the legend says how many, and each is in the
  endpoint layer). They are never part of an island, a weak point or a what-if: they forward
  nothing.
- **Every controller connection is a node**, its state and switch count under its name
  (`connected, 2 switches`; `couldn't read: <why>; 2 switches as last read`). A controller with
  no switch, as after a Mininet teardown, still draws itself (`connected, 0 switches`), never a
  blank map. Mercury is drawn reading it: a dashed line in the controller's colour labelled
  `northbound REST`, its card naming the address and port of the connection.
- **A host is one node per MAC on its switch port**, holding every address the controller
  learned for it, IPv4 beside IPv6. It is labelled by its global IPv4 address, else its global
  IPv6 address, else `host on <switch> port <n>`; a link-local address (`fe80::…`) is never the
  label. Its card lists the MAC and every address, the link-local ones marked. The same MAC
  listed on two ports is two nodes, each card saying where else it is listed. The header and
  the strip count hosts, never addresses.
- **A host is drawn only when its switch is in the same read.** The controller may still list
  hosts on switches it no longer has (Ryu keeps them until it restarts); they are not drawn and
  not located, and the strip counts them in words: `6 hosts reported by lab-ryu on switches no
  longer connected, not drawn`.
- **The Devices list** groups a controller's hosts under their switch, one closed group per
  switch (`of:…0001 · 3 hosts`); opening one lists each host's address, port, MAC and how many
  addresses it holds.
- **Above the map**, a strip names each source: LLDP's read time; each controller's read time
  and its switches, links and hosts; or `controller (<name>): couldn't read: <why>; its switches
  as last read at <time> (<age>)`. A controller that reports no link between two or more
  switches says so: none are cabled, or it discovers none (Ryu discovers links only when run
  with `--observe-links` and `ryu.app.rest_topology`). A controller without its topology
  application says "the topology app is not running", never "no links".

A host's place comes from the controller's host table: Ryu keeps a host until the controller
restarts and records no time, so a host it lists is one it learned since then, not necessarily
one there now. Mercury does not age a host out yet: the controller gives it no time to age it
by, so a host that left a port the switch still has stays drawn, named by its addresses or by
its port. The hosts feed the endpoint layer, so "which port is 192.0.2.10 on?" answers with the
switch and port (`of:…0001 port 2`), as its controller lists it.

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

A single point of failure or an only link the design intends (a course topology with one link
to an area border, say) can be **accepted**: **Accept…** asks why, as Mark as expected… does
for an island, needs a verified person, and is recorded on History with your name. It stays in
the weak points, drawn **accepted** with its reason and **Withdraw**, counted apart from the
ones to look at, and its SPOF tag leaves the map. What it cut off when accepted is kept with
it: if that changes (a device added behind it, a link gone), it warns again and says it was
accepted for another cut. Retiring a device withdraws every acceptance that names it.

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
