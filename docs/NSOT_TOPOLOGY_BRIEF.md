# Topology (P.11): the brief

Written 2026-10-04 from [the research](NSOT_TOPOLOGY_RESEARCH.md), for the operator's sign-off. It
answers the research's 21 open questions (its section 7) with a recommendation each, under the
seven headings the operator named: accuracy, stable positions, live state, layers, path trace,
failure impact, and wall and phone modes. The mockups are on the canvas ("NMAS v2 mockups", page
"P.11 Topology"). Nothing here is built; every decision below is a recommendation until signed off.

**What Topology answers** (P.11, the operator, 2026-09-30): how is it connected, what depends on
what, where is the weak point, how do I get from A to B. It is its own OBSERVE destination, the
whole screen, a starting point for navigation. One home: the Device page's Neighbours tab, an
alert and the deploy preview's what-if each OPEN it, centred and highlighted; none draws a second
copy.

## 1. The data and its accuracy

- **One reader job** (`readers/topology_graph.py`, the 7.2 pattern, 60 s) reads Prometheus's LLDP,
  OSPF, OSPFv3 and BGP series and `up`, plus NetBox's cables; builds one NetworkX `MultiGraph` per
  layer; computes the analyses; stores the value with its time; announces `topology` only on a
  change. Routes serve the stored value; nothing computes per request (Q13, Q14: the legacy
  `modules/topology.py` SSH discovery and the service's SVG retire with it; the agent's topology
  tool reads the stored value; the invalidation key is `topology`, redefined to mean this graph).
- **A link is the union of both ends' reports.** A link one end reports is drawn as such, and
  CLASSIFIED, never flagged wholesale (research 1.4: 4 of 11 links here are one-sided, two between
  polled devices): *far end not polled* (normal, said in grey), *both polled, one silent*
  (a finding only when it departs from that link's own measured history, kept by the reader), and
  *seen before, not now* (fading, then gone). **Recommended (Q4):** classify by polling first; a
  per-link baseline measured per network (never seeded from this lab's names); "recently" is 3
  LLDP scrapes (3 minutes at 60 s) for fading, 30 minutes for the changed marker.
- **The accuracy test (Q5).** NetBox cables here derive from LLDP (research 1.6), so they cannot
  check it. **Recommended:** a hand-kept fixture of the real cabling (`tests/fixtures/topology/
  cabling.yml`, the operator's, edited when the lab is re-cabled) is the independent expectation,
  and committed intent's interface descriptions a second, weaker one. The test compares the reader's
  graph from captured series against the fixture, link by link.
- **What it cannot see is said on the page:** links with no LLDP (a device with LLDP off), shared
  conduits and power (no SRLG data), and anything outside management.
- **Untrusted text (Q16):** every device-announced string (sysName, port descriptions, neighbour
  names) is escaped where drawn, with a test that plants markup in a captured series.

## 2. Stable positions

- **Saved positions, physics never on a refresh** (research 1.1, 1.2). A layout is computed once
  (layered by tier, then a constrained pass), saved, and only a person moves a node. A refresh moves
  nothing.
- **Positions are shared (Q1).** One layout per network, everyone sees the same map. Moving or
  pinning a node is a RECORDED act (who, when, from where to where), refused without a verified
  person, never an ungated write as today. **Recommended:** no personal layer at first; a person's
  zoom and centre are browser-local.
- **A new device (Q2)** appears in a "New" tray at the map's edge, beside nothing, until a person
  places it (one drag) or presses "Place beside its neighbours" (computed with every other node
  fixed). Nothing else moves.
- **Tiers (Q3):** from the NetBox role where the list is NetBox-sourced, else the inventory's role
  (core, edge, access...), mapped to bands top to bottom; a device with no role sits in an
  "unplaced" band. No new field.

## 3. Live state

- **Down is never colour alone (Q7, research 1.8):** a down link is drawn DASHED with a break mark
  and an "x" at its middle, red AND patterned; degraded (errors or discards over the device's own
  baseline) is a dotted line with a "!" badge. A node not answering is outlined and crossed.
  The legend is always on screen.
- **Which source wins per link:** link state from `ifOperStatus` at both ends (either end down =
  down, naming the end); speed from `ifHighSpeed` (added to the SNMP read: it is read nowhere today);
  utilisation from the octet counters at the end with telemetry when one streams.
- **Updates in place:** the page subscribes to `topology`; an edge already on screen changes when
  its state does (research 1.8: LibreNMS never updates one). Each state says its age on hover.
- **Device alarms (Q20):** a node carries Needs attention's highest open row as a corner badge
  (severity by shape and colour), acknowledged rows as a hollow badge.
- **Changed recently (Q21):** a link appearing or going, or a state flip, carries a "changed 4 min
  ago" marker for 30 minutes; a moved position is not a change of the network and carries none.

## 4. Layers

- **Switched, with physical underneath (Q18):** a selector chooses one of Physical (LLDP), OSPF,
  OSPFv3, BGP; the physical links stay drawn faintly under a routing layer, so an adjacency without
  a cable (or a cable without its adjacency) is visible. A link with several witnesses shows them on
  hover ("LLDP both ends, OSPF FULL, NetBox cable").
- **Disagreement is a finding** (research 1.3: no tool draws it): an OSPF adjacency intent implies
  (C427's direction: intended roles) and the graph lacks is drawn as a ghost line; a cable NetBox
  holds that LLDP never saw, likewise.
- **Parallel links and LAGs (Q6):** one line with a count ("x2") and the members on hover; the
  analysis keeps the MultiGraph, so a parallel link never reads as a bridge.

## 5. Path trace

- **What it claims (Q8):** the GRAPH's equal-cost shortest paths over the chosen layer, said as
  such: "every shortest path in the OSPF adjacency graph, by hop count", never a forwarding claim.
  Routing-table paths are a later step that reads the device's RIB, and would say so.
- **How:** pick A and B (click, or search, Q19: search matches name, address, role and interface,
  and zooms to the item, never filters the map away); every equal path is drawn, the rest dimmed;
  each hop lists its interfaces.

## 6. Failure impact

- **Single points of failure:** articulation points (devices) and bridges (links) on the MultiGraph,
  drawn with a ring and a "SPOF" label, listed in a side panel with what each would cut off
  ("s3 down: s4 loses its path to the management segment").
- **What-if (Q9):** take a device or link out on the map (a view, nothing sent): the islands that
  result are drawn and named. The management attachment point is CONFIGURATION (a setting naming
  the device or segment the tool reaches the fleet through), never a lab value. The result says what
  it could not see: shared conduits and power, protocols not read, devices outside management.

## 7. Wall and phone modes

- **Wall (Q10):** a read-only view at its own address, `/v2/topology/wall`, identity through an
  Access service token (a kiosk identity, never no login: C231's SVG must not be repeated); no
  control can change anything; labels sized for the viewing distance (20 to 22 minutes of arc:
  18 px at 2.5 m on a 1080p panel, a setting per wall); dark theme with the light-grey normal state
  of ISA-101 (normal recedes, abnormal stands out); the data's age always shown; a fixed view,
  no rotation, at first.
- **Phone:** below 700 px the default is the LIST of devices grouped by tier with their link counts
  and states (P.11 already decided), and the map is one tap away with pan and pinch-zoom; a node tap
  opens a sheet with its links and "Open device".

## 8. Time travel, scale, dependencies

- **Time travel (Q11):** the reader stores the graph only when it changes (SuzieQ's model), as a
  snapshot under `data/topology/` with its time, kept 90 days (the live retention); a slider steps
  between snapshots; the diff is staged (removals drawn first, then additions). "Not read" (the
  reader failed) is a gap in the slider, never a snapshot of an empty network.
- **Scale (Q12):** a NetBox-sourced list groups by site; a local list by tier; above 150 nodes a
  group collapses to a summary node with its counts and worst state.
- **Dependencies (Q15):** NetworkX (already on the host for the service) through the host-side lock;
  numpy and scipy only if the layout needs them; no ELK.
- **Drawing (research 1.10):** a spike compares Cytoscape.js and server SVG under the strict CSP,
  with these mockups as its acceptance; vis-network is not assumed.
- **Documents (Q17):** the GUI brief's "Devices > Topology" lines are corrected, and the manual page
  is written with the screen.

## For sign-off

The mockups (canvas page "P.11 Topology"): (A) the desktop map, OSPF layer over physical, an island,
a SPOF and a path trace; (B) the same at phone width, list first; (C) the wall view. The decisions
above are recommendations; the ones that most change the build are Q1 (shared, recorded moves), Q5
(the hand-kept cabling fixture), Q8 (graph paths, said so) and Q10 (a kiosk identity).
