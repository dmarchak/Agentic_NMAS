# Fidelity: Topology (P.11 step 2)

The page as built, compared region by region with its signed-off boards (C649, C650; the
operator, 2026-10-10). Read from shots of the board and the page side by side, in the same
headless Firefox, the page fed by the reader's value built from the real captures
(`tests/test_board_shots.py`, run with `NMAS_BOARD_SHOTS` and `NMAS_BOARDS_DIR`).

Boards: `TopoDesktop.dc.html` (1440 wide) and `TopoPhone.dc.html` (390 wide), on the mockups canvas (the operator's Design artifact), signed off 2026-10-04 (NSOT_STAGE7_PLAN 15.8 and 15.9). `TopoWall.dc.html` is a later step.
Shots: desktop 1440 and 1280; phone 390 (Firefox's narrowest window is 488 CSS px, so the page is held to a 390 px column; below 700 px the phone's rules apply to both). Compared 2026-10-10.
Compared again 2026-10-10 after the host walk (Mercury's host never a path between devices; the what-if names whom Mercury loses): the what-if panel's words changed, no region's verdict.
Templates compared: templates/v2/topology.html, templates/v2/_topology_map.html
Templates sha256: `aa8ef5b2bfbf05bd12280dc9dfe34d921c9200ff7d05942622a330d6efb3e329`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

## Desktop (TopoDesktop)

| Region | Board | Built | Verdict |
|---|---|---|---|
| Header | "Topology · Default · 9 devices, 14 links, 1 external · read 40 s ago"; Find; Wall view; How does this work? | the same line (the lab's counts), Find a device, address or interface, How does this work?; an info icon beside the title as on every v2 page | **same** |
| Wall view | a button | not drawn | **later** P.11's wall step; its kiosk identity is the operator's |
| Protocol toggles | OSPF, OSPFv3, BGP, RIP/RIPng, EIGRP, IS-IS | OSPF, OSPFv3, BGP, RIPng (not read); "Not read: EIGRP, IS-IS" | **deviation** (log: Topology's protocol toggles) |
| Ports, Labels, zoom, Weak points | Ports on; Labels Auto, On, Off; −, 100%, +; Weak points | the same; 100% is labelled Fit | **same** |
| Arrange | a button | not drawn | **later** step 3, saved and shared positions |
| Path…, Take out a device (what-if)… | buttons | each opens its question; its answer drawn in the side panel and on the map | **same** |
| Bands | CORE, EDGE, ACCESS, MANAGEMENT | the same four, measured from each device's class and outside peering | **deviation** (log: Topology's bands and L3 badge) |
| Device icons | router, switch (NMAS's own), Tabler for the rest; L3 badge | router and switch NMAS's own; server, cloud and dashed circle also NMAS's own; L3 badge | **deviation** (log: Topology's own icons) |
| Ports on links | the port at each end of every link | the port at each end of every link, placed clear of each other | **same** |
| State chips | "OSPF FULL", "BGP Estab", "OSPF 2WAY", "BGP Idle", "down", "RIP ?" | the same states with each protocol's key fact: "OSPF area 0: FULL", "eBGP AS 65002: Estab×2", a shared segment's counts, "down", "RIPng ?" | **deviation** (log: Topology's chips carry area and AS) |
| Line styles | green solid, orange dashed, thick red, grey dotted | the same four, the same meanings | **same** |
| What "not as intended" is | an OSPF 2WAY where FULL was intended | a link only one polled end reports, or a neighbour intent does not name; 2WAY is up | **deviation** (log: Topology counts 2WAY as up) |
| Outside peer | "r5 · ISP", a dashed cloud | "r5 · AS 65002", a dashed cloud | **deviation** (log: Topology names an outside peer by its AS) |
| Manager node | "manager", a server, in MANAGEMENT, linked to s3 Gi1/1 ↔ eth0 | "Mercury", a server, in MANAGEMENT, linked to s3 Gi1/1 ↔ the host's interface, measured | **deviation** (log: Mercury's host on the map, measured) |
| SPOF tag | a SPOF tag and a ring on s3, its words on hover | the same, its words naming Mercury, s3 Gi1/1 and VLAN 99 | **same** |
| Island tag | an island tag and a red border | the same | **same** |
| Hover card | title; Link with since; each protocol's state against intent; none on this link; read … from both · Neighbours | the same rows; since is the reader's own observation | **deviation** (log: Topology's since is observed) |
| Selected link | a blue glow | a blue glow, its card held open, its entry marked | **same** |
| Legend | 4 line styles and 9 device classes, over the map's foot | 4 line styles and 6 classes, below the map inside its box | **deviation** (log: Topology's own icons) |
| Needs attention on the map | count; All, down, not as intended, not read, weak points; filter; groups; entries with since | the same | **same** |
| Entry times | "since 21:02 UTC" | the product's time stamp: age, the exact time on hover; "at least since" when the state was so at the first read | **deviation** (log: Topology's since is observed) |
| Weak points | s3 SPOF with its words | s3 SPOF with its words, r6 island with Mark as expected…, the betweenness line | **deviation** (log: Topology keeps what the boards left out) |
| Zoomed out, a large fleet | an inset of a large fleet, icons and colours | this network zoomed out, labels off; above 150 devices no map | **deviation** (log: Topology's zoomed-out panel) |
| Footnote | the icons' licences | the icons (all Mercury's own), how a class is chosen, Mercury's measured place, what the map cannot see | **same** |
| Devices by band | not on the desktop board | a collapsed section below (the phone's Devices tab) | **deviation** (log: Topology keeps what the boards left out) |

## Phone (TopoPhone)

| Region | Board | Built | Verdict |
|---|---|---|---|
| Top bar | Menu · Topology · read 40 s ago | v2's own top bar (menu, network, search), then the page's header with its read time | **deviation** (log: Topology at phone width) |
| Tabs | Attention (5), Devices, Map | Attention (n), Devices, Map; Attention first | **same** |
| On the map | Ports: off, Labels: auto | the same, under the tabs | **same** |
| Counts | line samples with counts, weak points, n as intended | the same | **same** |
| Groups | down or a neighbour missing; up, not as intended; not read and weak points collapsed | the same groups; weak points open | **same** |
| Entries | both ends' icons, "r4 Gi4 ↔ r5 eth2", what is wrong | the same | **same** |
| Sheet | the selected link: ends with icons; Link, BGP, OSPF; r4's Neighbours, Show on the map | the same, held at the bottom; its grab closes it | **same** |
| Map tab | not drawn on the board | the whole map at its own size, scrolled sideways | **deviation** (log: Topology at phone width) |
