# Fidelity: Topology (P.11 step 2)

The page as built, compared region by region with its signed-off boards (C649, C650; the
operator, 2026-10-10). Read from shots of the board and the page side by side, in the same
headless Firefox, the page fed by the reader's value built from the real captures
(`tests/test_board_shots.py`, run with `NMAS_BOARD_SHOTS` and `NMAS_BOARDS_DIR`).

Boards: `TopoDesktop.dc.html` (1440 wide) and `TopoPhone.dc.html` (390 wide), on the mockups canvas (the operator's Design artifact), page "P.11 Topology: APPROVED 2026-10-04 (A to C)", approved as canvas version 34 on 2026-10-05 01:05 UTC with three fixes drawn on the same boards (NSOT_STAGE7_PLAN 15.8 and 15.9). `TopoWall.dc.html` is a later step.
Shots: desktop 1440 and 1280; phone 390 (Firefox's narrowest window is 488 CSS px, so the page is held to a 390 px column; below 700 px the phone's rules apply to both).
Compared 2026-10-10 (C649), and again the same day (C658: the operator, "those boards are what I want … fix every difference"). The first comparison marked 13 regions "deviation" and logged each as the agent's decision; C658 withdrew every one the board can be followed in (docs/STANDING_APPROVAL_LOG.md, C658's line). What remains different is listed below with its reason.
Compared again 2026-10-11 (C659: the operator, "route the Mercury–r6 (Gi2) link so it doesn't pass through r5's cloud or label"): the boards draw every link clear of the devices it does not join, and the host's map bowed Mercury's link to r6 through r5's cloud and name. A link is now drawn straight when it crosses no other device's icon, name or tag, else bowed the least that clears them all, either side, on the map; checked in a real browser on what it drew, on the captures and on the host's own layout. The templates changed only by data attributes naming each link's ends and each device; at 1440, 1280 and 390 no region's verdict changed. Walked on the host 2026-10-11 (222054b deployed 01:41 UTC; the host's own read, addresses removed): Mercury's link to r6 is drawn clear of r5's cloud and name, and the same browser check on the host's map finds no link crossing a device, name or tag it does not join, at 1440 and at 1280 (11 devices, 13 links).
Compared again 2026-10-11 (C661: the operator, "User should be able to move devices and save their topology … Remove the Access, Edge, Core, and Management sections", pan and wheel zoom, and five decisions). The three boards were redrawn first (canvas version 109: TopoDesktop's bands removed and its Arrange replaced by Reset layout with a line on moving, panning and zooming; TopoPhone's Map line; TopoWall's "the network's layout"), then the page compared with them at 1440, 1280 and 390. C659's crossing check runs on the new layout (the captures' spring layout and the host's stored one).
Walked on the host 2026-10-11 (335c0ee, deployed 03:25 UTC): the reader's first read laid the map out by springs (its layout carries a frame, no bands; 11 nodes), drawn from that stored document at 1440 and 390. The walk found the first view read 93% on a map taller than its box (the zoom measured by widths alone), hiding Labels Auto; fixed with C668 (the zoom against the true fit; the phone's readable floor only under 700 px), drawn again: 100%, every chip and port. Compared again for C668 (a selected link's card closes; the cards smaller). Compared again for C669 (2026-10-11: a saved layout that cannot be read is said under the map and Reset layout sets it aside; nothing the boards draw moved).
Templates compared: templates/v2/topology.html, templates/v2/_topology_map.html
Templates sha256: `b38497a9ac9e40e1e0788d1b775ae8de666ca24c77ae97648bf588694c99f2ce`

A verdict is **same**, **deviation** (a difference with its approval log line and its reason: data,
not design, or the operator's own decision), or **later** (a later step of the plan).

## Desktop (TopoDesktop)

| Region | Board | Built | Verdict |
|---|---|---|---|
| Header | "Topology · Default · 9 devices, 14 links, 1 external · read 40 s ago"; Find; Wall view; How does this work? | "Topology · Lab · 9 devices, 12 links, 1 external · read …"; Find (the field; Enter finds); How does this work?; an info icon beside the title as on every v2 page | **same** |
| Wall view | a button | not drawn | **later** P.11's wall step; its kiosk identity is the operator's |
| Protocol toggles | OSPF, OSPFv3, BGP, RIP / RIPng pressed; EIGRP, IS-IS not | the same six in the same order; EIGRP and IS-IS unpressed, their title saying Mercury does not read them | **same** |
| Ports, Labels, zoom, Weak points | Ports on; Labels Auto, On, Off; −, 100%, +; Weak points | the same | **same** |
| Reset layout (C661) | a button where Arrange was | the same; greyed out with its reason while nobody has moved a device, its "How does this work?" beside it | **same** |
| How to move, pan and zoom (C661) | a line at the top of the map: drag a device, drag empty space, the wheel or a pinch; who arranged it, when | the same words, above the map; "Arranged by" once someone has | **same** |
| Moving, panning, zooming (C661) | drawn as words (a board does not move) | a device dragged moves and the drop saves the map for everyone, recorded; empty space drags the view; the wheel and a pinch zoom at the pointer; the map sized to the window | **same** (walked in a real browser: tests/test_topology_v2.py) |
| Path…, Take out a device (what-if)… | buttons | each opens its question; its answer drawn in the side panel and on the map | **same** |
| Bands | none (redrawn for C661) | none | **same** |
| Where each device sits | an arrangement drawn by hand | the network's shared layout where people moved devices; elsewhere the cabling's springs from a fixed seed, each connected part on its own, an island beside the network | **deviation** (log: Topology's generated layout is a spring layout in plain Python): data, the board shows one arrangement; and the operator's decision named NetworkX's spring layout, which needs NumPy, a licence the project does not carry |
| Device icons | router and switch our own; Tabler for the rest; L3 badge | all our own (the operator, 2026-10-10: "your own icons are fine"); L3 badge | **deviation** (log: Topology's own icons): the operator's decision |
| Ports on links | the port at each end of every link | the same, placed clear of each other | **same** |
| State chips | one per protocol on a link, its two words: "OSPF FULL", "OSPFv3 FULL", "BGP Estab", "OSPF 2WAY", "BGP Idle", "down", "RIP ?" | the same two words for the neighbourship between the link's two ends; an adjacency only passing over a link (VLAN 100) gets a chip only when it is not as intended, naming both devices; "RIPng ?" where intent configures RIPng | **same** |
| Line styles | green solid, orange dashed, thick red, grey dotted | the same four, the same meanings | **same** |
| What "not as intended" is | an OSPF 2WAY where FULL was intended | the same (2WAY between two DROthers of a segment is what OSPF intends), and a link only one polled end reports | **same** |
| Outside peer | "r5 · ISP", a dashed cloud | "r5 · AS 65002", a dashed cloud | **deviation** (log: Topology names an outside peer by its AS): data, the fleet knows r5's AS, not that it is an ISP |
| Manager node | "manager", a server, in MANAGEMENT, linked to s3 Gi1/1 ↔ eth0 | "Mercury", the same, linked to s3 Gi1/1 ↔ the host's interface, measured | **deviation** (log: Mercury's host on the map, measured): data, the product's name |
| SPOF tag | a SPOF tag and a ring on s3, its words on hover | the same, its words naming Mercury, s3 Gi1/1 and VLAN 99 | **same** |
| Island tag | an island tag and a red border | the same | **same** |
| Hover card | title; Link with how long; a row per protocol, "OSPF area 0", its state and "intended FULL; since 20:58 UTC"; "BGP, RIPng: none on this link; none intended"; read … from both · Neighbours | the same rows; a VLAN 100 trunk's card also lists what passes over it | **same** |
| Selected link | a blue glow | a blue glow, its card held open, its entry marked; the card closes with its ×, a click on the map's empty space, or Escape (C668) | **same** (the board draws a selection, not how it ends) |
| Hover card's size (C668) | about 320 wide at 12.5 px | 250 wide at 11 px, a narrower term column (the operator, 2026-10-11: "the pop up text boxes are too large") | **deviation** (log: Topology's link card smaller than the board's) |
| Legend | 4 line styles and 9 classes | the same 4 and 9, below the map inside its box | **same** |
| Needs attention on the map | count; All, down, not as intended, not read, weak points; filter; groups; entries with since | the same | **same** |
| Entry times | "since 21:02 UTC" | the same ("at least since" when the state was so at the reader's first read) | **same** |
| Weak points | s3 SPOF with its words | the same, and r6's island with Mark as expected… | **deviation** (log: Topology keeps what the boards left out): the operator's requirement (an island declared expected, 30f8c1b) |
| Zoomed out, a large fleet | an inset of a sample large fleet; "Labels (Auto) appear as you zoom in…" | "Zoomed out": this network, icons and colours; the board's words, less "sites as groups", which the page does not draw | **deviation** (log: Topology's zoomed-out panel): data, this network is not a large fleet |
| Footnote | the icons' licences | the icons (all Mercury's own), how a class is chosen, Mercury's measured place, what the map cannot see | **same** |

## Phone (TopoPhone)

| Region | Board | Built | Verdict |
|---|---|---|---|
| Top bar | Menu · Topology · read 40 s ago | v2's own top bar (menu, network, search), then the page's title with its read time | **deviation** (log: Topology at phone width): the network picker and search live in v2's bar |
| Tabs | Attention (5), Devices, Map | Attention (n), Devices, Map; Attention first | **same** |
| On the map | Ports: off, Labels: auto | the same, under the tabs | **same** |
| Counts | line samples with counts, weak points, n as intended | the same, no All | **same** |
| Groups | small-capital headings: down or a neighbour missing; up, not as intended; not read and weak points collapsed | the same headings; weak points open, as the desktop board draws them (one list serves both) | **same** |
| Entries | full-width rows: both ends' icons, "r4 Gi4 ↔ r5 eth2", what is wrong | the same | **same** |
| Sheet | the selected link: ends with icons; Link, BGP, OSPF; r4's Neighbours, Show on the map | the same, held at the bottom; its grab closes it | **same** |
| Map tab | "Map: drag to pan, pinch to zoom. Devices are moved on a wider screen." (redrawn for C661) | the same words; the map starts readable (at least 0.6 px a map unit, centred) and pans and pinches; 100% fits the whole | **same** |
