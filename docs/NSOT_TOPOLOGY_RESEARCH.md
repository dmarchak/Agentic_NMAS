# Topology (P.11): research

Written 2026-10-01, and amended the same day after a completeness critique (sections 4.6 to 4.8 added;
citations, labels and caveats corrected). This is research only. Nothing is built from it yet. It feeds the topology brief
(`docs/NSOT_TOPOLOGY_BRIEF.md`, not yet written), then the mockups, then a spike that the operator
judges on how it feels.

**Already decided** (the operator's request): NetworkX analyses run on the server; the app draws the
map itself; Topology is its own page under OBSERVE; it has layers for LLDP links, OSPF adjacencies and
BGP sessions; and nothing may assume containerlab or this lab (the Stage 10 rule).

## Method

Six research streams ran. Each stream collected claims with their sources. A second reader then
checked every claim against its source, adversarially, and gave one of four verdicts: **confirmed**,
**corrected** (true once reworded; the corrected wording is the one used here), **refuted** or
**unverifiable**.

| Stream | What it covered | Claims | Confirmed | Corrected | Refuted | Unverifiable |
|---|---|---:|---:|---:|---:|---:|
| tools-oss | NetBox topology-views, LibreNMS, Zabbix | 57 | 50 | 7 | 0 | 0 |
| tools-vendor | SolarWinds, Cisco Catalyst Center, Arista CloudVision | 52 | 45 | 6 | 0 | 1 |
| tools-analysis | IP Fabric, Forward Networks, NetBrain, Auvik, Kentik, PRTG | 85 | 63 | 14 | 0 | 8 |
| themes | wall displays, layout stability, disagreement, path and impact, time travel | 88 | 69 | 16 | 0 | 3 |
| drawing | server SVG, Cytoscape.js, vis-network, sigma.js, d3-force, ELK.js | 72 | 63 | 9 | 0 | 0 |
| codebase | what this repository already has | 55 | 50 | 5 | 0 | 0 |
| **Total** | | **409** | **340** | **57** | **0** | **12** |

Rules this document follows:

- Only confirmed or corrected claims appear in sections 1 to 7. The 12 unverifiable ones appear only
  in section 8.
- Each claim cites its source inline: a URL, or `path:line` in this repository.
- **(opinion)** marks what a practitioner, reviewer or maintainer said, as opposed to what a document
  or the code states. People are named by role in the text, never by name. Some cited URLs carry a
  person's name (a LinkedIn post, a Zabbix Summit slide file); they are public sources, so the links are
  kept as they are.
- **(inference)** marks a conclusion drawn from the evidence rather than stated by a source.
- Limits: Reddit and the review sites (G2, Gartner Peer Insights, TrustRadius) refused to be fetched.
  Several vendor help pages render client-side and were read through a public reader service. There
  was no host access, so nothing here was run on the host or in a browser.

---

## 1. Summary: the ten things that matter most

1. **Saved positions; physics never runs on a refresh.** Pure physics layouts drew repeated complaints
   in both open-source tools (a judgement from the threads cited, not a count). NetBox's plugin "spins"
   ([#634](https://github.com/netbox-community/netbox-topology-views/issues/634)). A LibreNMS
   maintainer said its map "has always been broken" by physics (opinion,
   [thread](https://community.librenms.org/t/map-shaking/12668)). NetBox now caps the simulation and
   switches physics off once it settles
   ([home.js](https://github.com/netbox-community/netbox-topology-views/blob/develop/netbox_topology_views/static_dev/js/home.js#L71-L84)).
2. **Stability helps the tasks an operator actually does.** Experiments find that a stable drawing
   helps "map-like" tasks (locating a node, following a long path) when the nodes are not otherwise
   highlighted. It is not a general win ([GViP 2014](https://ceur-ws.org/Vol-1244/GViP-paper5.pdf);
   ["The Map in the mental map", IJHCS 2013](https://research.monash.edu/en/publications/the-map-in-the-mental-map-experimental-results-in-dynamic-graph-d/)).
3. **No tool surveyed draws disagreement between link sources on the map as a finding.** The nearest
   are IP Fabric's separate table of one-sided neighbours
   ([docs](https://docs.ipfabric.io/main/IP_Fabric_GUI/technology_tables/CDP_LLDP/)), Auvik's black
   "inferred" wires ([guide](https://www.auvik.com/wp-content/themes/auvik/downloads/Deployment-Guide-Customers.pdf)),
   Forward's present/absent link overrides ([API doc](https://docs.fwd.app/25.12/api-doc/)) and one
   third-party Zabbix module's confidence and ageing edges
   ([LLDP-SETUP.md](https://github.com/linuser/zabbix-network-topology/blob/main/LLDP-SETUP.md)).
   Nearer still, but about paths and snapshots rather than link sources: NetBrain draws the difference
   between the current path and a saved "golden" path on a map
   ([handbook](https://www.netbrain.com/wp-content/uploads/2019/11/NetBrain-Feature-Handbook.pdf)), and
   IP Fabric and Forward compare snapshots on or beside the diagram (section 4.5). No tool found compares
   link sources (LLDP, cables, routing adjacencies) on the map (inference).
4. **"Seen from one end = flagged" would flag this lab's normal state.** In the real LLDP capture,
   4 of 11 links are seen from one end only, and two of those join devices that are both polled
   (`tests/fixtures/topology/lldpRemEntry.json`; `docs/NSOT_PLAN.md:4224`). One-sided reports need
   classifying, not a blanket flag.
5. **LLDP carries no "last seen".** `lldpRemTimeMark` is `0` on all 18 rows of the capture
   (`tests/fixtures/topology/lldpRemEntry.json`). Prometheus drops a stale series from instant queries
   after 5 minutes ([querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)) and keeps
   15 days by default ([storage](https://prometheus.io/docs/prometheus/latest/storage/)). Link age and
   history must be kept by the reader, or recovered with range queries within retention.
6. **NetBox cables are not shown to be independent of LLDP here.** NMAS's import creates cables from
   live CDP/LLDP reads, and never corrects a re-cabled link (`modules/netbox_client.py:900-929`,
   `3103-3127`; register C100 on who made the existing cables). An accuracy test needs an expectation
   computed by an independent path (CLAUDE.md, the control rule).
7. **Single points of failure are a shipped feature and cheap to compute** ("cheap" is inference: both
   are linear-time graph searches by the standard algorithms, not measured here). IP Fabric draws
   articulation points red and marks bridges
   ([intent checks](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/intent_checks/)). NetworkX
   computes both, but only a `MultiGraph` keeps parallel links from reading as a bridge
   ([bridges](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.bridges.bridges.html)),
   and graph redundancy is not physical diversity ([RFC 4202, SRLG](https://www.rfc-editor.org/rfc/rfc4202.txt)).
8. **A down link must not be colour alone, and must update.** About 1 in 12 men have a colour-vision
   deficiency, mostly red-green ([NEI](https://www.nei.nih.gov/learn-about-eye-health/eye-conditions-and-diseases/color-blindness)),
   and WCAG 1.4.1 forbids colour as the only signal
   ([WCAG 2.2 SC 1.4.1](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)). Kentik draws
   "degraded" and "not working" the same dashed yellow ([KB](https://kb.kentik.com/docs/kentik-map)).
   LibreNMS's map never updates an edge already on screen (read from the code, not observed;
   [netmap.blade.php](https://github.com/librenms/librenms/blob/master/resources/views/map/netmap.blade.php#L143-L195)).
9. **A wall view is shared and read-only.** On a group display, critical information must not be
   changeable by passers-by, and anyone who needs their own changes gets a separate display; preferred
   character size is 20-22 minutes of arc ([FAA HFDS ch. 5](https://hf.tc.faa.gov/hfds/download-hfds/hfds_pdfs/Ch5_Displays_and_printers.pdf),
   5.1.2.15, 5.7.1). The existing topology SVG is already served to the internet with no login
   (`docs/OPEN_FINDINGS.md:304`, C231); a kiosk mode must not repeat that.
10. **Drawing: Cytoscape.js is the canvas library with the longest strict-CSP record; the vendored
    vis-network build does not fit the policy.** Cytoscape has supported `style-src 'self'` since 2019
    ([PR #2318](https://github.com/cytoscape/cytoscape.js/pull/2318)); its one `<style>` injection can
    probably be pre-empted (inference, untested). It is not the only clean option: sigma 3.0.3 has no eval
    and no `<style>` injection, and the needed d3 modules and server SVG are clean too (section 5.2). The
    vendored vis-network 9.1.6 is the standalone build, which injects its stylesheets at load
    (`static/js/vendor/vis-network/vis-network.min.js`); its peer build injects none. Server-drawn SVG is
    the most accessible and probably the easiest to theme (inference: it themes by stylesheet classes
    where the others need colours fed from JavaScript). The spike decides (section 5).

---

## 2. How established tools present topology

### 2.1 NetBox: the topology-views plugin (open source, Apache-2.0)

- **What it draws.** Only NetBox's documented records, never discovered state: cables, logical
  interface connections through patch panels (dashed yellow), circuit terminations, wireless links and
  power connections. It exports draw.io XML or PNG
  ([README](https://github.com/netbox-community/netbox-topology-views/blob/develop/README.md#L5-L8);
  [views.py](https://github.com/netbox-community/netbox-topology-views/blob/develop/netbox_topology_views/views.py#L198)).
- **Layout.** vis-network (^10.1.2) with the forceAtlas2Based solver, capped at 1,000 iterations, then
  physics switched off for every node. Nodes with no saved coordinate start at (0,0)
  ([home.js](https://github.com/netbox-community/netbox-topology-views/blob/develop/netbox_topology_views/static_dev/js/home.js#L71-L84)).
- **Persistence.** Off by default: `allow_coordinates_saving` defaults to False, so a default install
  re-lays the map out on every load. When on, a dragged device's position is saved and the device leaves
  the physics. Positions are kept per named Coordinate Group, shared by everyone; there is no per-user
  layout ([README](https://github.com/netbox-community/netbox-topology-views/blob/develop/README.md#L104-L108), L152, L184).
- **Live state.** None. The node border is the role colour, the edge is the cable's documented colour,
  and device status exists only as a filter. The maintainer describes the scope as "filter devices and
  connect them with the given cables" (opinion, [#717](https://github.com/netbox-community/netbox-topology-views/issues/717)).
- **Disagreement.** None possible: no LLDP, CDP or routing code at all. Its "cable integrity check" only
  stops a crash on a half-connected cable ([#646](https://github.com/netbox-community/netbox-topology-views/issues/646)).
- **Scale.** Filters, "Show Neighbors", rectangles around devices of one site, location, rack or virtual
  chassis, and snap-to-grid. No collapse. Requests to merge parallel links
  ([#122](https://github.com/netbox-community/netbox-topology-views/issues/122), open since 2022) and
  to show only the critical cable path
  ([#405](https://github.com/netbox-community/netbox-topology-views/issues/405), open since 2023) are
  unresolved
  ([forms.py](https://github.com/netbox-community/netbox-topology-views/blob/develop/netbox_topology_views/forms.py#L649-L712)).
  A request to space site rectangles so they do not overlap was closed as not planned
  ([#494](https://github.com/netbox-community/netbox-topology-views/issues/494)).
- **Performance.** A 3-node-plus-neighbours query on 1,500+ devices and 10,000+ cables generated about
  3,500 database queries and took about 23 s; larger selections timed out. Closed as not planned
  ([#723](https://github.com/netbox-community/netbox-topology-views/issues/723)).
- **Path and impact.** None. A whole-path request was closed as not planned because finding all
  devices on a multi-device path was judged too hard; a path-highlighting proof of concept was closed
  unmerged ([#455](https://github.com/netbox-community/netbox-topology-views/issues/455)).
- **Security.** An open PR fixes stored XSS: device, cable and site fields were put into tooltip HTML
  unescaped and rendered through `innerHTML` ([#740](https://github.com/netbox-community/netbox-topology-views/pull/740)).
- **Maintenance.** Active: v4.7.0 on 2026-09-18
  ([release](https://github.com/netbox-community/netbox-topology-views/releases/tag/v4.7.0)), about 1,099
  stars ([GitHub API](https://api.github.com/repos/netbox-community/netbox-topology-views), read
  2026-10-01). Each release pins a NetBox version, and the README warns that an unlisted NetBox version
  "will most likely not work"
  ([README L55-56](https://github.com/netbox-community/netbox-topology-views/blob/develop/README.md#L55-L56)).
  NetBox Labs lists it as a certified built-in plugin of NetBox Enterprise, at 4.5.1
  ([built-in plugins](https://netboxlabs.com/docs/enterprise/nbe-ec-built-in-plugins)).
- **The commercial alternative.** NetBox Assurance compares ingested network data with NetBox and shows
  "deviations" with change analysis and proposed remediation. It is an add-on to Enterprise or Cloud,
  not available in Community Edition; its docs do not say whether cables or LLDP are compared
  ([docs](https://netboxlabs.com/docs/assurance/)).

### 2.2 LibreNMS (open source, GPLv3)

- **Network Map: sources.** Links come from xDP (FDP, CDP or LLDP) and from MAC/ARP matching. The docs
  warn that a large map draws and responds slowly, and point to per-device neighbour maps and
  device-group maps ([Network-Map.md](https://github.com/librenms/librenms/blob/master/doc/Extensions/Network-Map.md)).
- **Layout.** vis-network force simulation (forceAtlas2Based, physics on, fixed random seed 2). Nothing
  saves positions. In September 2026 the tunable options were replaced by hard-coded defaults
  ([PR #20574](https://github.com/librenms/librenms/pull/20574)), 13 days after a settings GUI for them
  was merged ([PR #20128](https://github.com/librenms/librenms/pull/20128))
  ([NetworkMapOptions.php](https://github.com/librenms/librenms/blob/master/LibreNMS/Util/NetworkMapOptions.php#L36-L97)).
- **Live state.** A link is dashed in the down colour when either port is down or both devices are
  down. Otherwise it is coloured by utilisation (the max of in and out, 5% steps) and its width grows
  with the digit count of its speed, roughly logarithmically
  ([MapDataController.php](https://github.com/librenms/librenms/blob/master/app/Http/Controllers/Maps/MapDataController.php#L683-L720)).
  On the timed refresh (default 300 s), nodes update but an edge already on screen never does, so a
  link that goes down after the page loads keeps its old colour until a full reload (read from the
  code, not observed; [netmap.blade.php](https://github.com/librenms/librenms/blob/master/resources/views/map/netmap.blade.php#L143-L195)).
  Utilisation is read from one end's port only
  ([MapDataController.php](https://github.com/librenms/librenms/blob/master/app/Http/Controllers/Maps/MapDataController.php#L706)).
- **Disagreement.** xDP and MAC links are merged per port pair, and the edge records no source. Nodes
  with no link are hidden ([MapDataController.php](https://github.com/librenms/librenms/blob/master/app/Http/Controllers/Maps/MapDataController.php#L637-L730)).
- **Scale.** Device-group maps, a per-device neighbour map, "Highlight Node", a slow-render warning above
  500 devices, and a full-screen geographic map that can aggregate links per location pair and groups
  markers by area ([netmap.blade.php](https://github.com/librenms/librenms/blob/master/resources/views/map/netmap.blade.php#L107-L108)).
- **Impact.** Only over hand-configured parent/child dependencies: a top-down Dependency Map (physics
  off) with "Highlight Dependencies to Root Device" and "Highlight All Child Devices", and alert
  suppression for children while all their parents are down. Nothing is derived from discovered links
  ([device-dependency.blade.php](https://github.com/librenms/librenms/blob/master/resources/views/map/device-dependency.blade.php#L14-L25)).
- **Custom Maps** (the documented replacement for Weathermap). Hand-built by admins, aligned to a grid,
  saved only when "Save Map" is pressed; every viewer sees the change at their next refresh. A node can
  link to another map for drill-down. Each half of a link carries its own direction's utilisation colour,
  green through yellow and red to purple at 150%+
  ([Custom-Map.md](https://github.com/librenms/librenms/blob/master/doc/Extensions/Custom-Map.md);
  [CustomMapDataController.php](https://github.com/librenms/librenms/blob/master/app/Http/Controllers/Maps/CustomMapDataController.php#L97-L130)).
  The docs say a down link is black and an idle one green; the code draws a down port dark red and an
  idle 0% link black, the same colour as an unknown speed (L323-330).
- **Wall.** `?bare=yes` hides the menu bar "for a monitoring screen on a TV"; `screenshot=yes` strips all
  labels from a Custom Map ([Bare-Dashboard.md](https://github.com/librenms/librenms/blob/master/doc/Support/Bare-Dashboard.md)).
- **Maintenance.** The maps broke twice in 2026: the network and dependency maps would not load in
  26.9.1 when `web_mouseover` was disabled (fixed 2026-09-30,
  [forum](https://community.librenms.org/t/network-and-dependency-map-broken-after-last-update-26-9-1/29479)),
  and the Network Map was reported broken in May 2026
  ([#19691](https://github.com/librenms/librenms/issues/19691)).

### 2.3 Zabbix (and two third-party additions)

- **Native maps.** Hand-built, fixed-coordinate SVG. Elements are dragged into place, optionally on a
  grid, and coordinates and grid options are saved with the map. Nothing re-lays out, but nothing lays
  out automatically either ([map config](https://www.zabbix.com/documentation/current/en/manual/config/visualization/maps/map)).
  The only automatic placement is a host group element expanded with the "Grid" algorithm, which ignores
  the area's shape ([host groups](https://www.zabbix.com/documentation/current/en/manual/config/visualization/maps/host_groups)).
- **Live state.** An element in problem gets a circle in the highest severity's colour, a thick green ring
  when every problem is acknowledged, an orange square in maintenance, a grey one when disabled, and red
  inward triangles for 30 minutes after a recent change
  ([monitoring maps](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/monitoring/maps)).
  Links take a style and colour from triggers (highest severity wins, ties to the lowest trigger ID) or,
  since 7.4, from an item value crossing a threshold. Labels can show live values through macros
  ([links](https://www.zabbix.com/documentation/current/en/manual/config/visualization/maps/links)).
- **Sources.** Links exist because someone drew them; nothing comes from LLDP or discovery. A 2012
  request for auto-generated maps was judged to have "very low probability of being implemented"
  ([ZBXNEXT-1333](https://support.zabbix.com/browse/ZBXNEXT-1333)). Collecting LLDP over SNMP is
  awkward because the LLDP-MIB remote table's index changes on every link-up, and past neighbours are
  not kept ([Summit 2018 slides](https://assets.zabbix.com/files/zabsummit2018/Takeshi_Tanaka-Monitoring_and_Visualization_of_LLDP_information_in_Zabbix.pdf)).
- **Scale.** A host group element can summarise every host's triggers in one icon; a sub-map element
  shows a whole map's status; the Map navigation tree widget sums sub-maps' problems
  ([map tree](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/dashboards/widgets/map_tree)).
- **Wall.** Every Monitoring page, maps included, has a kiosk mode (also `kiosk=1` on dashboards), and
  dashboards rotate pages as a slideshow ([dashboards](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/dashboards)).
- **Impact and time.** No path trace or what-if on maps. Impact is modelled as trigger dependencies,
  which withhold dependents' notifications; they are configured, not drawn
  ([dependencies](https://www.zabbix.com/documentation/current/en/manual/config/triggers/dependencies)).
  Maps show current state only; the 30-minute markers are the nearest thing to "what changed".
- **Accessibility.** A map exposes a screen-reader summary, for example "Local network, 1 of 6 elements
  in problem state, 1 problem in total ..." ([monitoring maps](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/monitoring/maps)).
- **A third-party module** for Zabbix 7.0/7.4 (AGPL-3.0, built on Cytoscape.js) fills the gaps: edges
  from LLDP/CDP, "what-if" failure simulation (right-click a host, every host that loses its path turns
  red), a computed path as a list, a severity-only history slider capped at 7 days, live refresh every
  30 s, a wallboard mode, and saved layout in two layers, an administrator's shared one and a personal
  one ([README](https://github.com/linuser/zabbix-network-topology/blob/main/README.md)). It is the most
  complete example found of a map showing source and doubt (Auvik's wire colours, IP Fabric's distinct
  manual links and Forward's override colours, sections 2.7, 2.8 and 2.10, show parts of it): LLDP neighbours not in Zabbix appear as dashed "ghost nodes"
  naming who reported them; a hand-declared edge carries lower confidence than a reported one and is
  completed, not duplicated, if a device later reports it; edges age instead of vanishing; and an
  ambiguous match draws nothing ([LLDP-SETUP.md](https://github.com/linuser/zabbix-network-topology/blob/main/LLDP-SETUP.md)).
  Its own docs warn that a wrong hand-drawn edge makes the simulation "reliably wrong", reporting hosts
  as safe that are not. It escapes every LLDP neighbour name, because a rogue device can announce
  `<script>`.
- **An LLDP-to-Zabbix-map generator** writes maps through the API by overwriting a map of the same name,
  so regenerating discards any hand placement (inference, [repo](https://github.com/TiggyWiggler/zabbix-map)).

### 2.4 SolarWinds (Network Atlas, Intelligent Maps, NetPath)

- **Network Atlas** (Windows desktop editor) is deprecated in favour of Intelligent Maps
  ([docs](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-interpreting-map-links-sw3458.htm)).
  A migration tool arrived in 2024.2 without full parity, and staff said Atlas would stay until parity
  was satisfactory ([thwack](https://thwack.solarwinds.com/discussion/102171/network-atlas-to-orion-maps-and-when-will-network-atlas-be-removed)).
  Atlas offered one-shot layouts (Circular, Symmetrical, Hierarchical, Orthogonal, Tree)
  ([docs](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-selecting-automatic-layout-styles-sw3521.htm)).
  Down links are always red; up links take a chosen colour
  ([map links](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-interpreting-map-links-sw3458.htm));
  utilisation colour is the default and is never shown on a hand-drawn link
  ([docs](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-determining-interface-performance-sw3404.htm)).
  ConnectNow draws links from a topology table recalculated every 30 minutes by default, and can link to
  "unidentified nodes" seen in topology data but not managed
  ([docs](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-connecting-objects-automatically-with-connectnow-sw3389.htm)).
- **Sources.** Orion merges CDP, LLDP, ARP and CAM data polled over SNMP into one set of connections;
  nothing found shows which source made a link ([KB](https://support.solarwinds.com/SuccessCenter/s/article/Network-topology-considerations)).
- **Intelligent Maps: layout.** Auto-generated maps add and remove entities as the network changes, and
  "layouts and other changes do not persist". A saved map keeps its positions
  ([intro](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-orion-maps-intro.htm)).
  Layouts: Grid, Hierarchical and Force-Directed for selected entities; placed items snap to a grid
  ([create](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-orion-maps-create-maps.htm)).
- **Live state.** Width is interface bandwidth; colour turns yellow past a warning threshold and red past
  critical; a ring shows entity health; a "metric pill" on a link shows outbound traffic and utilisation
  ([connections](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-orion-maps-connections.htm)).
  By design the pill switches to errors and discards when those cross a threshold, and a practitioner
  did not recognise the new number until a product manager pointed at the inspector
  ([thwack](https://thwack.solarwinds.com/discussion/104857/connections-on-intelligent-maps-change-display)).
  Clicking opens an inspector; the selected object's connections are highlighted
  ([NPM onboarding](https://documentation.solarwinds.com/en/success_center/npm/content/onboarding/custom_views_maps/npm_ob_orion_maps.htm)).
- **Time.** "Historical Tracking" scrubs or replays a map's past status at 10-minute snapshots over
  7 days, opt-in per map, at most 10 maps and 100 entities per map. The doc does not say whether topology
  changes are replayed ([time travel](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-orion-maps-time-travel.htm)).
- **Scale.** Nested maps for drill-down and group status roll-up (worst, best, mixed); object count
  affects map speed ([nested maps](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-orion-maps-nested-maps.htm)).
- **Wall.** A dashboard "NOC view": compressed header and footer, no left navigation, a dark theme only in
  NOC view, tabs rotating every 15 s by default with pause and resume
  ([NOC views](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-noc-views-dark-modern-dashboards.htm)).
  Putting maps on it takes specific setup (one map per tab, one-column layout, matched palettes)
  ([KB](https://support.solarwinds.com/SuccessCenter/s/article/Intelligent-Maps-not-available-in-NOC-view-maps-not-rotating-in-the-SolarWinds-Platform)).
  Map widgets on Modern Dashboards did not refresh in 2025.2 and earlier, so a wall could look live and
  be stale, while tables beside it refreshed ([KB](https://support.solarwinds.com/SuccessCenter/s/article/Intelligent-Maps-Map-on-Modern-Dashboard-doesn-t-refresh)).
- **Impact.** Dependencies: children of a down parent read "Unreachable" instead of "Down" and raise no
  down-node alert; with several parents, only when all are down
  ([dependencies](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-managing-dependencies-sw1688.htm)).
- **NetPath** is a measured, probe-based hop-by-hop path drawn left (source) to right (destination),
  green/yellow/red per hop, a dotted line to an unreachable host, networks grouped into collapsible
  circles, and a timeline to see the path at a past interval
  ([docs](https://documentation.solarwinds.com/en/success_center/npm/content/npm-view-a-network-path.htm)).

### 2.5 Cisco Catalyst Center

- **Placement.** Topology is its own tool (Tools > Topology), separate from the health dashboards. It
  opens a Cisco-recommended layout; users save several named layouts, set one as default, share them and
  export SVG, PDF or PNG ([3.1 guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-1-x/user_guide/b_cisco_catalyst_center_user_guide_3_1_x/b_cisco_catalyst_center_ug_3_1_x_chapter_0101.html)).
- **Layout by role.** The physical map is laid out from each device's role, assigned at discovery or
  changed in inventory; older releases had hierarchical layouts over Core, Distribution, Access, Border
  Router and Unknown ([1.0 guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/dna-center/1-0-x/b_dnac_ug_1_0/b_dnac_ug_1_0_chapter_0111.html)).
  The API keeps, per node, whether its position is fixed or auto-laid-out, its x/y, whether it is greyed
  out, and whether its role was set by hand; links carry up/down and per-end port name, speed and
  address ([API](https://developer.cisco.com/docs/dna-center/get-topology-details/)).
- **Scale.** Devices aggregate into groups and links into aggregated links (click lists the members); a
  device can be pinned out of its group; nearby sites cluster with a count on the geographic view
  ([2.3.7 guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/2-3-7/user_guide/b_cisco_catalyst_center_user_guide_237/b_cisco_dna_center_ug_2_3_7_chapter_0101.html)).
  Filters highlight a VRF, VLAN, routing protocol (IS-IS, OSPF, EIGRP, static), tags, or PRP
  redundancy; "Redundancy" is PRP status, not a single-point-of-failure analysis.
- **Live state.** Opt-in display layers, Device Health and Link Health; a down link is red
  ([3.1 guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-1-x/user_guide/b_cisco_catalyst_center_user_guide_3_1_x/b_cisco_catalyst_center_ug_3_1_x_chapter_0101.html)).
  Health colours are fixed score bands: 1-3 red, 4-7 orange, 8-10 green, 0 grey for no data
  ([Assurance 3.1](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center-assurance/3-1-x/b_cisco_catalyst_assurance_3_1_x_ug/b_cisco_catalyst_assurance_3_1_x_ug_chapter_0110.html)).
- **Sources.** CDP, with LLDP only where CDP is not configured; no conflict display was found. Inventory
  (devices, links, interfaces) re-polls every 24 h by default plus a resync on a config-change trap, so a
  re-cabling with no config change may wait for the next poll (inference,
  [2.3.7 guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/2-3-7/user_guide/b_cisco_catalyst_center_user_guide_237/b_cisco_dna_center_ug_2_3_7_chapter_011.html)).
- **Path.** Path Trace is computed from collected topology and routing data, not measured; it labels each
  hop (Switched, STP, ECMP, Routed, Trace Route), shows ACL permit/deny in green/red, can refresh every
  30 s, and lists many unsupported cases (third-party devices, NAT and firewalls, ECMP over SVI, dual
  stack, VSS, vPC) ([Assurance 2.3.7](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center-assurance/2-3-7/b_cisco_catalyst_assurance_2_3_7_ug/b_cisco_catalyst_assurance_2_3_6_ug_chapter_01111.html)).
- **Time.** Assurance's "time travel" is a health and issues timeline: up to 14 days in the 2.3.7
  datasheet ([datasheet](https://www.cisco.com/c/en/us/products/collateral/cloud-systems-management/dna-center/nb-06-dna-center-data-sheet-cte-en.html)),
  up to 30 days in the 3.1 guide. No documentation was found for viewing the topology map itself at a
  past time.

### 2.6 Arista CloudVision

- **Layout from metadata, not physics.** Topology is built from LLDP plus tags. The documented
  correction is "tag hints" (role, network type, containers), after which CloudVision re-arranges the
  affected devices; no drag-and-save was found ([topology edit](https://www.arista.io/help/articles/topology-edit)).
  The Hierarchy Manager places devices by tag rules (first match wins), sorts containers alphanumerically
  left to right, and stacks roles by a fixed weighting: core/super-spine, spine, leaf, host
  ([lab guide](https://labguides.testdrive.arista.com/2025.3/campus/intermediate_l3ls/lab7_topo_custom/)).
- **Honest about doubt.** Devices it cannot place go into "Untagged" and "Unclassified" buckets, and the
  vendor tells users to check the generated topology and correct it
  ([overview](https://www.arista.io/help/articles/overview-cloudvision)). Unmanaged devices include
  inactive ones, so a device that stopped reporting probably stays on the map as unmanaged (inference
  from the word "inactive"; [2024.2 topology](https://www.arista.io/help/2024.2/articles/dG9wb2xvZ3kuQWxsLnRvcG9sb2d5)).
- **Scale and live state.** Nested containers (data centre, pod, rack, campus, cloud) shown at the top
  level first; more than 20 overlays, each a colour scale with an on-screen key and hover for exact values
  (bandwidth utilisation, active events, flow data) (same page).
- **Path.** Flow-based: flows seen by sFlow, IPFIX or in-band telemetry are drawn "in Topology", refreshed
  every 30 s, only where flow telemetry is on ([flows](https://www.arista.io/help/articles/devices-traffic-flows)).
- **Time.** Time Comparison shows one device's state at two moments, LLDP neighbours included, as tables
  ([comparison](https://www.arista.io/help/2024.3/articles/ZGV2aWNlcy5jb21wYXJpc29uLkFsbA==)). A
  topology at a past time is claimed only in a press release
  ([PR](https://www.arista.com/en/company/news/press-release/19195-pr-20240305)).

### 2.7 IP Fabric (snapshot-based assurance)

- **Layout.** Six automatic layouts (circular, downwardTree, hierarchical, radial, universal, upwardTree),
  settable per site ([blog](https://ipfabric.io/blog/api-programmability-part-4-diagramming/)), and
  applicable to a selected set of devices
  ([network viewer](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/network_viewer/)). Positions
  persist only when a person saves a "User-Defined Layout", which can become the site's default; only
  visible nodes' positions are saved. Named views can be saved and shared as a URL. Circular is limited to
  500 nodes, and since 7.2.5 a circular graph above 100 nodes uses "universal" instead
  ([7.2 release notes](https://docs.ipfabric.io/7.5/releases/release_notes/7.2/)).
- **Touch.** Pinch to zoom, tap to select and drag nodes are documented for touch and desktop
  ([network viewer](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/network_viewer/)).
- **Scale.** Sites are clouds opened by double-click; any selection can collapse into a new cloud or be
  hidden; parallel protocol links group into one line; devices collapse into L2 or L3 groups; search
  filters and zooms to the item. Sites come from rules (hostname or SNMP location regex), and an
  unmatched device inherits its site from its CDP/LLDP, STP or L3 neighbours
  ([site separation](https://docs.ipfabric.io/latest/IP_Fabric_Settings/Discovery_and_Snapshots/Discovery_Settings/site_separation/)).
- **Disagreement.** One-sided neighbours are separated: "unmanaged" (the far end is not accessible) and
  "unidirectional" (only one side sees the neighbourship), as tables; whether the diagram marks them is
  not documented ([CDP/LLDP](https://docs.ipfabric.io/main/IP_Fabric_GUI/technology_tables/CDP_LLDP/)).
  Hand-documented links are drawn distinctly from calculated ones; a manual link whose device was not
  discovered shows the status "Failed" in Snapshot Settings, not on the diagram ([manual links](https://docs.ipfabric.io/main/IP_Fabric_Settings/Discovery_and_Snapshots/Discovery_Settings/manual_links/)).
- **Path and impact.** Single points of failure are built-in checks: articulation points drawn red and
  bridges marked, computed without regard to protocol or direction
  ([intent checks](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/intent_checks/)), also scoped to
  one end-to-end path ([blog](https://ipfabric.io/blog/spotting-single-points-of-failure/)). Path lookup
  colours each device by what it did (red blocked, green permitted, blue forwarded, amber flooding, grey
  cloud/WAN); at a denying rule a person chooses Drop or Continue ("not applied")
  ([path lookup](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/how_to_use_path-lookup/)). Intent
  results overlay green/yellow/red ([blog](https://ipfabric.io/blog/network-topology-diagrams-over-spreadsheets/)).
- **Live state.** None found: it shows a snapshot (daily or triggered); an independent reviewer called it
  an "Observed Source of State" (opinion, [write-up](https://www.linkedin.com/pulse/network-field-day-23-ip-fabric-peter-welcher)).
- **Time.** Pick a snapshot; up to 5 loaded in memory (100 with PostgreSQL), and loading one takes
  minutes ([snapshots](https://docs.ipfabric.io/latest/overview/snapshots/)). "Compare Snapshots" on a
  diagram shows what changed ([compare](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/compare_snapshot/)).
  The docs warn that comparing a partial snapshot with a full one produces "many false positives",
  because missing data reads as removal.
- **Drawing.** The API returns a diagram as server-rendered SVG or PNG bytes, or JSON: a precedent for
  drawing the graph on the server ([blog](https://ipfabric.io/blog/api-programmability-part-4-diagramming/)).

### 2.8 Forward Networks (snapshot-based assurance)

- **Sources.** Links come from LLDP/CDP, from inference over learned MAC addresses, and from user
  overrides, which win. An override says a link is "present" or "absent"
  ([API doc](https://docs.fwd.app/25.12/api-doc/)). Deleting a link in the view removes it from the model
  itself ([community](https://community.forwardnetworks.com/search-topology-and-decorators-61/deleting-links-from-the-topology-view-where-do-they-go-320)).
  Overrides show as Applied, Staged (applied at the next snapshot) or Unsaved, each in its own colour
  ([links](https://docs.fwd.app/latest/application/topology/topolayout/links/)).
- **Gaps named.** Path search names a device missing from the snapshot and asks for it; the stated method
  is to find the "last point of agreement" between expected and computed paths
  ([community](https://community.forwardnetworks.com/path-search-85/path-search-what-to-do-when-your-search-query-returns-an-unexpected-result-501)).
  "Synthetic nodes" stand in for parts that cannot be collected, such as a provider L3VPN
  ([community](https://community.forwardnetworks.com/synthetic-nodes-70/introduction-to-forward-networks-synthetic-nodes-547)).
- **Layout and scale.** Devices map to user-defined locations (unmapped go to "Unassigned"), can be
  clustered, and since 26.1 can be placed by glob patterns on names ([community](https://community.forwardnetworks.com/general-discussions-38/automatically-assign-devices-to-locations-using-a-wildcard-glob-674)).
  Auto Layout plus align, distribute, rotate and JSON import/export
  ([docs](https://docs.fwd.app/latest/application/topology/topo-onprem-infra/)); whether saved positions
  survive a new snapshot is not documented.
- **Layers.** Physical, L2, L3, BGP and OSPF views from a selector. L2 draws STP forwarding green and
  blocking dotted red; parallel L3 links collapse into one line with a circled count; OSPF is coloured by
  area ([layers](https://docs.fwd.app/latest/application/topology/topology-layers/)).
- **Wall.** 26.1 added dark mode across the product, topology included, naming long-running wall displays
  as a reason; the choice (Light, Dark, Auto) is saved per user
  ([community](https://community.forwardnetworks.com/general-discussions-38/dark-mode-is-now-available-across-the-forward-platform-666)).
- **Time.** Diffs between two snapshots list topology links added and removed ([diffs](https://docs.fwd.app/latest/application/diffs/)).
  How a topology diff is drawn on the map was not found.
- **Naming.** Forward's "blast radius" is a security feature (what a compromised host can reach), not
  failure impact ([PDF](https://forwardnetworks.com/wp-content/uploads/2021/11/BlastRadius-1.pdf)).

### 2.9 NetBrain

- **Layout by role.** Four kinds: By Tag (a device's tag names its layer, such as core), By Sample
  (positions saved from another map), By Geometry (six shapes, hierarchical among them) and By Logic
  ([layout types](https://www.netbrain.com/docs/12tp0fe0ge/help/HTML/layout-types.html)). A layout can be
  saved as a sample by hostname position ([sample](https://www.netbrain.com/docs/ie80/help/creating-a-sample-layout.htm)).
- **Scale.** A site hierarchy on one overview map with double-click drill-down to L2 or L3, and "Dynamic
  Zoom" showing more detail as you zoom in ([handbook](https://www.netbrain.com/wp-content/uploads/2019/11/NetBrain-Feature-Handbook.pdf)).
- **Provenance.** Hovering a map element shows the configuration section that produced it (same
  handbook). Gaps are repaired by hand-added links and "fix-up" links for devices without LLDP/CDP
  ([fix-up](https://www.netbrain.com/docs/10df1cb15d/help/HTML/view-and-add-vlan-fix-up-link-for-a-specific-device.html)).
- **Live state.** Data Views and an Overall Health Monitor highlight CPU, memory, interface up/down and
  traffic; a value breaking its baseline turns red, with historical values beside it
  ([golden baseline](https://www.netbrain.com/docs/ie80/help/golden-baseline-analysis-result.htm)).
- **Path and time.** A/B path from live data, history, or against a saved "golden" path, drawn as an L2/L3
  map with the differences shown; paths can be re-verified with alerts on change (handbook). Scheduled
  "benchmarks" feed a Compare tab and change analysis; updated maps keep restorable timestamped backups
  ([scheduling](https://www.netbrain.com/docs/10df1cb15d/help/HTML/scheduling-map-update.html)). No
  single-point-of-failure analysis or wall mode was found.

### 2.10 Auvik, Kentik, PRTG

- **Auvik.** Wire colour says how a link was established: solid blue for a confirmed Layer 1 link, solid
  black for an inferred one, purple for VPN, dotted blue for Wi-Fi
  ([archived help](https://web.archive.org/web/2024id_/https://support.auvik.com/hc/en-us/articles/204908674-Your-network-map)).
  Its deployment guide treats a mostly-black map as a sign of missing data
  ([guide](https://www.auvik.com/wp-content/themes/auvik/downloads/Deployment-Guide-Customers.pdf)).
  It collapses subtrees into a node with a count badge, has a full-screen map, and tells users to raise
  the session timeout on a large display (archived help). Marketing claims a map that can be rewound
  "to the offending moment" ([page](https://www.auvik.com/network-management-software/network-mapping-software/)).
  Its path view hides every node not on the path
  ([article](https://www.networkworld.com/article/3510844/auvik-adds-visualization-tool-to-its-network-management-platform.html)).
- **Kentik.** Links can be coloured by utilisation with a legend; a degraded or not-working link is a
  dashed yellow line ([KB](https://kb.kentik.com/docs/kentik-map)). The L2 map is built from LLDP polled
  every three hours ([KB](https://kb.kentik.com/docs/router-configuration)). The logical map splits a
  two-way link into segments sized by the traffic ratio ([KB](https://kb.kentik.com/docs/logical-map)).
- **PRTG.** Maps are drawn entirely by hand ([map designer](https://www.paessler.com/manuals/prtg/map_designer)).
  A connection line takes colour from the status of the objects at its ends, half and half when they
  differ. A map can be published at a URL with a changeable secret key and scaled to the screen
  ([settings](https://www.paessler.com/manuals/prtg/maps_settings)).

### 2.11 Open and analysis tools worth borrowing from

- **SuzieQ** builds each edge as an outer merge of per-source observations (LLDP, BGP Established, OSPF
  full, and ARP/ND on request), with one true/false column per source and a "polled" column that is false
  when the peer is not polled itself ([topology.py](https://raw.githubusercontent.com/netenglabs/suzieq/develop/suzieq/engines/pandas/topology.py)).
  It stores a record only when it changes ([time](https://suzieq.readthedocs.io/en/latest/time/)).
- **Netdisco** keeps neighbour-map positions per filtered view (device, groups, locations, VLAN, depth)
  ([NetmapPositions.pm](https://raw.githubusercontent.com/netdisco/netdisco/master/lib/App/Netdisco/DB/Result/NetmapPositions.pm)),
  keeps hand-entered links in their own table ([Topology.pm](https://raw.githubusercontent.com/netdisco/netdisco/master/lib/App/Netdisco/Web/Plugin/AdminTask/Topology.pm)),
  and ships a 2,500-device map ceiling and a `node_label_zoom_threshold` setting, which presumably shows
  labels only past a zoom level (inference from the setting's name; [config.yml](https://raw.githubusercontent.com/netdisco/netdisco/master/share/config.yml)).
- **Netdata** states that each link carries its evidence, how it was discovered and how confident it is
  ([docs](https://learn.netdata.cloud/docs/network-performance-monitoring/topologies)).
- **Batfish** answers "what if this fails" by forking a snapshot with nodes or interfaces switched off and
  diffing reachability ([notebook](https://batfish.readthedocs.io/en/latest/notebooks/linked/analyzing-the-impact-of-failures-and-letting-loose-a-chaos-monkey.html)).
- **Nagios** marks hosts behind a failed parent UNREACHABLE rather than DOWN, to find the root cause
  ([docs](https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/networkreachability.html)).
- **ThousandEyes** ties its path graph to a timeline; links over a latency threshold turn red, nodes over a
  loss threshold get a red ring, and dense paths collapse by aggregation
  ([docs](https://docs.thousandeyes.com/product-documentation/internet-and-wan-monitoring/path-visualization)).

### 2.12 Comparison

| Tool | Layout and stability | Live state | Source disagreement | Scale | Wall mode | Path / failure impact | Time travel |
|---|---|---|---|---|---|---|---|
| NetBox topology-views | Physics, then off; saved positions opt-in, shared groups | None | None (records only) | Filters, site/rack boxes; no collapse | None found | None | None |
| LibreNMS Network Map | Physics on, fixed seed; nothing saved | Down dashed; utilisation colour; edges never refresh | Sources merged, unattributed | Group and neighbour maps, geo map | `bare=yes` | Manual dependency tree | None |
| LibreNMS Custom Maps | Hand-placed, saved by admin | Per-direction utilisation colour | Hand-drawn | Linked maps | `bare=yes`, `screenshot=yes` | None | None |
| Zabbix native | Hand-placed, fixed coordinates | Severity circles, trigger/item link styles, 30 min change markers | Hand-drawn | Host-group icons, sub-maps, map tree | Kiosk, slideshow | Trigger dependencies (not drawn) | Current only |
| Zabbix third-party module | Saved shared + personal layers | 30 s refresh | Ghost nodes, confidence, ageing edges | Not documented here | Wallboard | What-if, path list | 7-day severity slider |
| SolarWinds Intelligent Maps | Auto maps re-lay out; saved maps persist | Width = bandwidth; yellow/red; metric pill | Merged, unattributed | Nested maps, roll-up | NOC view, rotation, dark | Dependencies; NetPath (measured) | 10-min snapshots, 7 days, 10 maps |
| Catalyst Center | Default + saved named layouts; per-node fixed flag | Opt-in health layers; down red | CDP preferred, LLDP fallback | Aggregated devices and links | None found | Path Trace (computed) | Health timeline 14-30 days; no map history |
| CloudVision | Deterministic from tags and role weighting | 20+ overlays with key | Untagged / Unclassified buckets | Nested containers | None found | Observed flows | Device Time Comparison |
| IP Fabric | Six layouts; saved user layout | None (snapshots) | Unidirectional / unmanaged tables; manual links distinct | Site clouds, link and layer grouping | None found | SPOF red; simulated path colours | Snapshots, compare on diagram |
| Forward | Auto layout; persistence undocumented | None found | Present/absent overrides; missing-device hints | Locations, clusters, globs | Dark mode for walls | Path search, decorators | Snapshot diffs (links added/removed) |
| NetBrain | Role tags, samples; saved | Data Views, health monitor | Configlet on hover; fix-up links | Site hierarchy, dynamic zoom | None found | Live/historical/golden path | Benchmarks, Compare |
| Auvik | Not confirmed | Colour-coded health (marketing) | Blue confirmed vs black inferred | Collapse with count | Full screen + timeout advice | Path view | "Rewind" (marketing) |
| Kentik | Not found | Utilisation colour; degraded = down = dashed yellow | Not found | Location clusters | Not found | Not found | Time-range control only |
| PRTG | Hand-placed | Half-and-half line by end status | Hand-drawn | Not found | Public URL, scale to fit | None | None found |

---

## 3. What practitioners praise and complain about

All of this section is **(opinion)**.

**Praise**

- A third-party guide calls NetBox topology-views "the #1 most-installed visualization plugin" (a
  secondary opinion, [netodata.io](https://netodata.io/netbox-plugins-guide-2026-the-step-by-step-resource/)).
  Users value its draw.io export enough to chain it into Visio
  ([#714](https://github.com/netbox-community/netbox-topology-views/discussions/714)).
- LibreNMS users on Custom Maps: "Just wanna say what a wonderful feature custom map is", and asked for it
  as a dashboard widget ([forum](https://community.librenms.org/t/cusomt-map-feature/23729)).
- A Zabbix reviewer: "The map screen is also really useful because this is something that was missing"
  ([PeerSpot](https://www.peerspot.com/questions/what-do-you-like-most-about-zabbix)).
- An independent engineer (stating the post is not sponsored) praises IP Fabric's filtering by site,
  routing or switching, and its end-to-end path view
  ([post](https://www.packetswitch.co.uk/ip-fabric-automated-network-assurance-platform/)). Another
  reviewer values that its diagrams stand in for missing or old documentation
  ([write-up](https://www.linkedin.com/pulse/network-field-day-23-ip-fabric-peter-welcher)).
- NetBrain reviewers rate automatic mapping its most valuable feature, including "mapping of what's
  actually configured vs. what the network architect intended" ([PeerSpot](https://www.peerspot.com/products/netbrain-reviews)).

**Complaints**

- **Maps that will not hold still.** NetBox plugin users: nodes snap back and float
  ([#73](https://github.com/netbox-community/netbox-topology-views/issues/73)); saved positions reload
  slightly offset ([#117](https://github.com/netbox-community/netbox-topology-views/issues/117)); the
  topology spins
  ([#634](https://github.com/netbox-community/netbox-topology-views/issues/634)). Coordinate saving
  failed repeatedly across versions and deployments
  ([#577](https://github.com/netbox-community/netbox-topology-views/discussions/577)). At multi-site scale
  everything "tends to bunch up and pull towards 0,0" ([#603](https://github.com/netbox-community/netbox-topology-views/issues/603)).
  The plugin's draw.io export placed every node at (0,0), "tedious ... for a network with a couple
  hundred nodes" ([#435](https://github.com/netbox-community/netbox-topology-views/discussions/435)).
  LibreNMS users: the map "doesn't seem to want to settle"
  ([shaking](https://community.librenms.org/t/map-shaking/12668)), is "shaky and all over the place"
  ([Map freaking out, 2018](https://community.librenms.org/t/map-freaking-out/5638)), and "is getting reset
  at every refresh" with "no save topology option"
  ([save](https://community.librenms.org/t/network-map-save-option/24026)). A LibreNMS maintainer, in the
  shaking thread: "I'm currently not working on it as we never look at this map anyway", the most telling
  opinion found on that map ([shaking](https://community.librenms.org/t/map-shaking/12668)). A NetBrain
  operator found a map's links changed after a scheduled benchmark although "Always auto link all
  devices" was switched off ([forum](https://exchange.netbrain.com/general-46/site-map-limitations-214)).
- **Maps that are wrong.** LibreNMS's MAC mode produced "a big unusable fur ball"; LLDP behind a switch
  that forwards LLDP frames drew "weird and incorrect loops"; the map is "better than nothing but
  incomplete and a bit inaccurate in places"; and nobody could say what thin versus thick lines meant
  ([forum](https://community.librenms.org/t/network-map-device-groups-and-customisation/15873)). Auvik
  reviewers: the map "can be messy when a network is unnecessarily complex", "struggles to bring the
  connections up correctly", clutters at around 700 sites, and once generated "is a static view and you
  can't remove or rearrange devices" ([PeerSpot](https://www.peerspot.com/questions/what-advice-do-you-have-for-others-considering-auvik)).
- **Discovery overriding what a person documented.** SolarWinds users (2020-2021): an automatic
  connection "just assumes switch to switch" and "will not disappear"; it is "all or nothing"; "the maps
  are useless in our environment unless they can either discover all the connections, or allow us to
  delete those that we don't want"; one team disabled CDP on every switch to stop it
  ([thwack](https://thwack.solarwinds.com/products/network-performance-monitor-npm/f/forum/88276/disable-topology-auto-connections-on-orion-maps)).
  A newer thread finds auto-connections "one of the most frustrating aspects" of the new maps, link
  direction invisible, and the platform "extremely not polished"
  ([thwack](https://thwack.solarwinds.com/discussion/152397/creating-and-edit-intelligent-maps-questions)).
  Catalyst Center users cannot add an unmanaged device or a hand-drawn link, which they had in Prime
  Infrastructure ([community](https://community.cisco.com/t5/cisco-catalyst-center/dna-center-topology-add-unmanaged-devices-links/td-p/4390127)).
- **Hand-placement is tedious.** Zabbix: wiring each link to its triggers "takes a very long time"; one
  user with 500+ hosts added three-pixel images as fake waypoints to route links, "a very hard and
  annoying work" ([ZBXNEXT-7853](https://support.zabbix.com/browse/ZBXNEXT-7853)). Parallel links between
  two hosts draw on top of each other (ZBXNEXT-442, open since 2010). PRTG's designer cannot multi-select
  or align ([request](https://helpdesk.paessler.com/en/support/solutions/articles/76000077017-looking-at-we-need-a-new-map-designer)),
  and one user named the lack of a weather map as the reason not to replace Cacti
  ([request](https://helpdesk.paessler.com/en/support/solutions/articles/76000075893-feature-request-for-maps)).
- **Scale.** A NetBrain community answer: "Go for a maximum of 50 devices per map and even that might be
  too many" ([forum](https://exchange.netbrain.com/general-46/map-hierarchy-108)). A NetBrain user asks
  for layout over a hand-picked group, since the tools act only on one device or the whole map
  ([idea](https://exchange.netbrain.com/ideas/1223)). A Grafana user asks for "zoom to fit data" because
  refreshing a large node graph leaves an awkward zoom ([#128622](https://github.com/grafana/grafana/issues/128622)).
- **Wall screens.** A former NOC designer (2011): analysts "always look at the event viewer at their
  desk. The big wall of screens is purely to impress customers/investors during visits"
  ([Hacker News](https://news.ycombinator.com/item?id=3334608)). A practitioner who deployed 400+ 24/7
  displays advises signage-rated screens that will not burn in, and warns that Raspberry Pi players
  usually run an older Chromium on which modern front-end code may fail
  ([Hacker News](https://news.ycombinator.com/item?id=30870661)).
- **Speed and reliability.** Network Atlas maps took "3-5 seconds to load"
  ([thwack](https://thwack.solarwinds.com/discussion/comment/69455)); newly saved Intelligent Maps hung
  on an endless spinner ([thwack](https://thwack.solarwinds.com/discussion/104790/intelligent-maps-issue));
  DNAC 2.3.3.5 did not show all links even after rediscovery
  ([community](https://community.cisco.com/t5/software-defined-access-sd-access/topology-link-not-working-on-dnac/m-p/5034788)).

---

## 4. Cross-cutting themes

### 4.1 Wall displays

- **Size by distance.** The preferred character size is 20-22 minutes of arc, so characters grow with
  viewing distance; maximum viewing distance is set by legibility (HFDS 5.1.2.14-15,
  [PDF](https://hf.tc.faa.gov/hfds/download-hfds/hfds_pdfs/Ch5_Displays_and_printers.pdf)). ISO
  9241-303 places presentation viewing at typically 2-10 m ([sample](https://cdn.standards.iteh.ai/samples/57992/bddfd91165b444f6b9815a6993feadc5/ISO-9241-303-2011.pdf)).
  Arithmetic, for scale: 20 arc minutes at 3 m is about 17.5 mm; on a 55-inch 4K panel (about 0.32 mm per
  pixel) that is about 55 px. At 5 m it is about 29 mm. A label sized for a desktop is too small on a wall.
- **Shared and read-only.** On a group display, the most distant viewer must resolve critical detail,
  critical information must not be changeable inadvertently, changes are under designated users, and a
  person who needs their own changes gets a separate display (HFDS 5.7.1.3, 5.7.1.5-5.7.1.7). So a wall
  view takes no drag and no per-user path trace; investigation happens on a personal screen (inference).
  A rotation configured by designated users is compatible with this.
- **How tools do it.** SolarWinds' NOC view (compressed chrome, rotation, dark only there); Grafana's
  playlists with kiosk mode and "auto fit panels" ([playlists](https://grafana.com/docs/grafana/latest/dashboards/create-manage-playlists/));
  Datadog's TV mode fits all widgets without scrolling by an enforced aspect ratio, and warns that zooming
  to fill the screen makes fonts hard to read at distance ([TV mode](https://docs.datadoghq.com/dashboards/guide/tv_mode/));
  Zabbix kiosk; LibreNMS `bare=yes`. Grafana's advice: refresh as often as the data changes, not more,
  and reduce cognitive load ([best practices](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/)).
- **Identity is its own problem.** Grafana ships a separate utility whose jobs include logging an
  unattended kiosk device in ([grafana-kiosk](https://github.com/grafana/grafana-kiosk)), and Auvik tells
  users to raise the session timeout for a large display. Here identity is a Cloudflare Access assertion,
  so an unattended wall needs the Access service-token path and must be able to change nothing (docs/LESSONS.md#route-gates-and-verified-identity,
  "Automation uses a Cloudflare Access service token"; "A verified service is still not a person")
  (inference).
- **Colour only on what is wrong.** Secondary descriptions of ISA-101 high-performance HMI use a grey
  normal state with colour reserved for abnormal conditions, and one says the background should be "Light
  grey, not white and not dark blue" ([RealPars](https://www.realpars.com/blog/high-performance-hmi);
  [LADX](https://ladx.ai/resources/isa-101-hmi-design)). That is in tension with the request for a dark
  wall mode; it argues at least for colour only on what is wrong (inference).
- **Ownership on the board.** A research big-board design shows each problem's ownership as well as its
  type (red flag unassigned, yellow being worked) and which missions it affects
  ([arXiv 1412.3768](https://arxiv.org/abs/1412.3768)).

### 4.2 Layout stability and the mental map

- **The definition.** "Preserving the mental map" is usually credited to "Layout Adjustment and the
  Mental Map" (JVLC 6(2), 1995). It is most often taken to mean existing nodes and edges move as little
  as possible when the graph changes ([IJHCS 2013 abstract](https://research.monash.edu/en/publications/the-map-in-the-mental-map-experimental-results-in-dynamic-graph-d/)).
- **The evidence is mixed, and favours this use.** A 2013 synthesis found no conclusive evidence that
  stability helps dynamic graph comprehension in general (same source). Later work found it does help
  map-like tasks, locating nodes and following long paths, when five or more relevant nodes are not
  otherwise highlighted, and that pinned positions help users see the order of additions and removals
  ([GViP 2014](https://ceur-ws.org/Vol-1244/GViP-paper5.pdf)). An early experiment found stability helps
  for some categories of task ([Graph Drawing 2006](https://eprints.gla.ac.uk/35828)). 2D desktop views
  beat immersive 3D for tasks needing spatial memory, while the same study found immersive views let
  people read network structure more accurately, especially on larger networks
  ([arXiv 2001.06462](https://arxiv.org/abs/2001.06462)).
  Finding a device, following a path and seeing what is downstream are map-like tasks, so saved positions
  are supported here (inference). Caveat: a path trace that highlights its hops weakens the stability
  benefit for that task.
- **Practice.** Where positions persist, a person saved them: IP Fabric's user-defined layout, NetBrain's
  samples, NetBox's opt-in coordinates, Netdisco per filtered view, LibreNMS Custom Maps, Zabbix by
  construction. CloudVision derives placement deterministically from tags, roles and container names, so a
  device moves when those change. Catalyst Center keeps a per-node "fixed" flag. **None of the docs found
  says how a new device enters a saved layout without disturbing the rest; the brief must specify it.**
- **Mechanisms for "place only what is new".** NetworkX `spring_layout` takes initial positions, a fixed
  set and a seed ([docs](https://networkx.org/documentation/stable/reference/generated/networkx.drawing.layout.spring_layout.html));
  `multipartite_layout` places nodes in layers keyed on an attribute
  ([docs](https://networkx.org/documentation/stable/reference/generated/networkx.drawing.layout.multipartite_layout.html)).
  Cytoscape's fCoSE takes fixed-position, alignment and relative-placement constraints, added
  incrementally ([README](https://github.com/iVis-at-Bilkent/cytoscape.js-fcose)). ELK's semi-interactive
  crossing minimisation keeps the order within a layer, not the coordinates, so existing nodes can still
  shift ([option](https://eclipse.dev/elk/reference/options/org-eclipse-elk-layered-crossingMinimization-semiInteractive.html)).
- **The viewport too.** Stable positions are not enough if each refresh re-zooms (the Grafana request in
  section 3).
- **This repository today.** The topology service recomputes the whole layout on every build and saves
  nothing, so one added link can move every node (`deploy/topology/rcn-topology.py:199-208`, inference
  on the effect). The legacy map saves positions, but prunes the saved position of any device that was
  offline at the last discovery (section 6).

### 4.3 Showing disagreement and confidence

- **One-sided is not one thing.** IP Fabric separates "unmanaged" (far end not reachable) from
  "unidirectional" (both reachable, one sees the other); SuzieQ marks whether the peer is polled. An LLDP
  port can be legitimately receive-only or transmit-only, so a one-way report can be configuration
  ([lldpd](https://lldpd.github.io/usage.html)).
- **In this lab, one-sided between polled devices is normal.** r1 reports s1 while s1 reports only s2, and
  r2 reports s2 while s2 reports only s1; both switches are polled with their LLDP scrape up. r3-r5 and
  r4-r5 are one-sided because r5 is retired (`tests/fixtures/topology/lldpRemEntry.json`, `up.json`;
  `docs/NSOT_PLAN.md:4221-4226`). A blanket "unidirectional = finding" would flag the lab's normal state,
  so the rule needs a measured baseline or per-platform knowledge.
- **Age.** lldpd's defaults give a neighbour a 120 s TTL ([lldpd](https://lldpd.github.io/usage.html));
  the scrape interval adds to it. Prometheus marks an unscraped series stale and drops it from plain
  instant selectors after 5 minutes
  ([querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)); a range query can still
  find its last sample within retention, 15 days by default
  ([storage](https://prometheus.io/docs/prometheus/latest/storage/)). LLDP's own time mark is `0` here
  (`tests/fixtures/topology/lldpRemEntry.json`).
- **The lab's one-sided pairs are evidence, not design values.** The device names above (r1, s1, r2, s2,
  r5) describe the captured data. The brief must not carry them, or a baseline built from them, as
  design values (the Stage 10 rule; question 9 in section 7 says the same of the manager's attachment
  point).
- **How tools draw confidence.** Auvik by wire colour; Forward by override state colours; IP Fabric
  manual links drawn distinctly with "Failed" when the device is missing; Netdata says each link carries
  its evidence (no encoding documented); NetBrain shows the configuration a link came from; CloudVision's
  Untagged and Unclassified buckets; the third-party Zabbix module's ghost nodes, confidence and ageing
  edges, and its rule that an ambiguous match draws nothing. The NetBox plugin names only the record type.
  A SolarWinds "red dashed line" may mean the topology calculator could not confirm a drawn connection,
  but that rests on an unverified excerpt (section 8).
- **Protocols other than LLDP.** SuzieQ's per-source columns (LLDP, OSPF full, BGP Established) are the
  closest model of "one link, several witnesses", and they are a table, not a drawing. Forward switches
  layers and can show physical links under the L3 and OSPF views. No tool was found that compares
  routing adjacencies (OSPF, BGP) with LLDP links on the map and draws the difference.
- **Untrusted text.** LLDP and CDP names are announced by other devices, so they are untrusted input;
  the third-party Zabbix module escapes every one, enforced by CI
  ([README](https://github.com/linuser/zabbix-network-topology/blob/main/README.md)). The legacy map here
  does not (section 6).

### 4.4 Path trace and failure impact

- **"Path" means three different things.** Catalyst Center computes it from collected topology and
  routing data; SolarWinds NetPath measures it with probes; CloudVision draws flows it observed. IP Fabric
  simulates it hop by hop with a per-hop decision; NetBrain compares it with a saved "golden" path.
  The brief must say which kind P.11's path is (P.11 says "never a forwarding claim",
  `docs/NSOT_PLAN.md:4208-4296`).
- **Several equal paths.** NetworkX `all_shortest_paths` returns every shortest path, with weights from an
  edge attribute such as OSPF cost; a missing attribute counts as 1
  ([docs](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.generic.all_shortest_paths.html)).
  SuzieQ lists equal paths by ID and says its path does not work in every case (some EVPN)
  ([docs](https://suzieq.readthedocs.io/en/latest/analyzer/)).
- **Single points of failure.** Articulation points and bridges, undirected only. `bridges()` ignores
  multi-edges only on a `MultiGraph`; on a plain `nx.Graph` two LAG members collapse into one edge and
  read as a bridge ([bridges](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.bridges.bridges.html)).
  The current renderer builds an `nx.Graph`. IP Fabric's result ignores protocols and direction, so an L1
  redundant pair need not be L3 redundant (inference). Two fibres in one conduit share a risk the graph
  cannot see ([RFC 4202 section 2.3](https://www.rfc-editor.org/rfc/rfc4202.txt)); a "no single point of
  failure" result should say what it could not see.
- **What if this fails.** Batfish forks the model with the element removed and diffs reachability. The
  third-party Zabbix module greys the failed host and reds every host that loses its path, and warns that
  a wrong edge makes it reliably wrong. Nagios and SolarWinds mark what is behind a failure "unreachable",
  not "down". Zabbix users have asked since 2012 for alerts that name the root problem
  ([ZBXNEXT-1461](https://support.zabbix.com/browse/ZBXNEXT-1461)). Forward's "blast radius" is a
  security term and is better not borrowed. No major vendor's what-if on the map was found.

### 4.5 Time travel

- **Two families.** Snapshot tools (IP Fabric, Forward, NetBrain benchmarks) are strong at comparison;
  monitoring tools (Kentik, PRTG) show live state with little history. NetBrain and (in marketing) Auvik
  claim both.
- **Bounds.** SolarWinds tracks 10-minute snapshots for 7 days on 10 maps; Catalyst Center's health
  timeline runs 14 to 30 days; NetBox's change log keeps 90 days by default
  ([config](https://netboxlabs.com/docs/netbox/configuration/miscellaneous/)); Prometheus 15 days.
  Snapshots the reader stores itself are bound by none of these.
- **Store changes, not runs.** SuzieQ stores a record only when it changes; P.11 already plans "a snapshot
  per CHANGE (not per run)" (`docs/NSOT_PLAN.md:4271`).
- **Absent is not removed.** IP Fabric warns that comparing a partial snapshot with a full one gives many
  false positives. A diff must tell "not read" from "gone".
- **Drawing the change.** GraphDiaries stages a transition (removals marked red, then the layout adapts,
  then additions marked blue) and beat a flip-book and plain animation on time and errors for several
  tasks ([TVCG 2014](https://aviz.fr/~bbach/graphdiaries/Bach2013GraphDiaries.pdf)). Caveat:
  GraphDiaries also bundles non-linear navigation, so its gain cannot be attributed to staged transitions
  alone. In Archambault, Purchase and Pinaud (IEEE TVCG 17(4), 2011), as reported second-hand in
  [GViP 2014](https://ceur-ws.org/Vol-1244/GViP-paper5.pdf), small multiples were significantly faster than
  interactive animation for every task tested, but with no difference in errors for three of them, and
  animation reduced errors when counting how often a node or edge was added (which the authors attribute
  to highlighting). The 2011 paper itself was not read.
  On a large touch display, timeslicing helped compare distant points in time
  ([arXiv 2008.12747](https://arxiv.org/abs/2008.12747)). Zabbix's 30-minute markers are a cheap "what
  changed recently" cue on the live map.

### 4.6 Live-state encoding

- **Width.** SolarWinds draws width as interface bandwidth, "so that you can easily determine
  differences between a 1 GB link, 10 GB link, or 100 MB link"
  ([connections](https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-orion-maps-connections.htm)).
  LibreNMS's Network Map uses twice the digit count of the speed in 10 Mb/s units, roughly a logarithm
  ([MapDataController.php](https://github.com/librenms/librenms/blob/master/app/Http/Controllers/Maps/MapDataController.php#L683-L720)).
  A LibreNMS user could not say what thin versus thick lines meant (opinion,
  [forum](https://community.librenms.org/t/network-map-device-groups-and-customisation/15873)), so width
  needs a key.
- **Direction.** LibreNMS Custom Maps colour each half of a link by its own direction's utilisation
  ([CustomMapDataController.php](https://github.com/librenms/librenms/blob/master/app/Http/Controllers/Maps/CustomMapDataController.php#L97-L130));
  Kentik's logical map splits a two-way link into segments sized by the traffic ratio
  ([KB](https://kb.kentik.com/docs/logical-map)). A SolarWinds user complained that ingress versus egress
  cannot be told apart (opinion,
  [thwack](https://thwack.solarwinds.com/discussion/152397/creating-and-edit-intelligent-maps-questions)).
- **Thresholds.** SolarWinds turns a connection yellow past a warning threshold and red past critical
  (connections page above). ThousandEyes turns a link red past a latency threshold and rings a node red
  past a loss threshold ([docs](https://docs.thousandeyes.com/product-documentation/internet-and-wan-monitoring/path-visualization)).
  CloudVision draws every overlay as a colour scale with an on-screen key and hover for exact values
  ([2024.2 topology](https://www.arista.io/help/2024.2/articles/dG9wb2xvZ3kuQWxsLnRvcG9sb2d5)).
- **Device alarms.** Zabbix puts a circle in the highest active severity's colour behind an element, a
  thick green ring when every problem is acknowledged, and red inward triangles for 30 minutes after a
  recent change ([monitoring maps](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/monitoring/maps)).
  A research big-board design shows ownership too: a red flag for an unassigned problem, yellow once it
  is being worked ([arXiv 1412.3768](https://arxiv.org/abs/1412.3768)). Catalyst Center's device health
  uses fixed score bands, grey for no data (section 2.5).
- **A number that changes meaning.** SolarWinds' metric pill switches from utilisation to errors and
  discards when those cross a threshold, by design, and a practitioner did not recognise the new number
  (opinion, [thwack](https://thwack.solarwinds.com/discussion/104857/connections-on-intelligent-maps-change-display)).
- **Down links differ by tool.** Kentik: dashed yellow, the same as "degraded"
  ([KB](https://kb.kentik.com/docs/kentik-map)). PRTG: red when both ends are down, half and half when the
  ends differ ([map designer](https://www.paessler.com/manuals/prtg/map_designer)). LibreNMS Network Map:
  dashed in the down colour (MapDataController above). LibreNMS Custom Maps: dark red in the code, black
  in the docs, and black also means "speed unknown" (section 2.2). Catalyst Center: red (section 2.5).
  Network Atlas: always red (section 2.4). This repository's topology service: red and dashed when either
  end node is down (`deploy/topology/rcn-topology.py:249-253`). An "unmistakable" down link rules out
  Kentik's choice, and colour alone fails the colour-vision and WCAG points in section 1, item 8
  (inference).
- **Colour only on what is wrong.** The ISA-101 descriptions in section 4.1 argue for a grey normal state
  and colour reserved for the abnormal (inference for this map).

### 4.7 Scale and search

- **Collapse into a node.** Auvik collapses subtrees or common devices into one node with a count badge,
  expanded one at a time or all at once
  ([archived help](https://web.archive.org/web/2024id_/https://support.auvik.com/hc/en-us/articles/204908674-Your-network-map)).
  IP Fabric draws sites as clouds opened by double-click and lets any selection collapse into a new cloud
  ([network viewer](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/network_viewer/)). Catalyst
  Center aggregates devices into groups and lets one device be pinned out of its group (section 2.5).
  CloudVision nests containers (section 2.6). Zabbix summarises a host group in one icon and a sub-map in
  one element (section 2.3). SolarWinds nests maps and rolls group status up (section 2.4).
- **Collapse parallel links.** IP Fabric groups a layer's protocols into one line; Forward collapses
  parallel L3 links into one line with a circled count
  ([layers](https://docs.fwd.app/latest/application/topology/topology-layers/)); Catalyst Center
  aggregates links and lists the members on click. NetBox's plugin (#122) and Zabbix (ZBXNEXT-442) users
  still ask for it (section 3).
- **Ceilings and warnings.** Netdisco's map ships a 2,500-device ceiling
  ([config.yml](https://raw.githubusercontent.com/netdisco/netdisco/master/share/config.yml)); LibreNMS
  warns above 500 devices that the first render will be slow
  ([netmap.blade.php](https://github.com/librenms/librenms/blob/master/resources/views/map/netmap.blade.php#L107-L108));
  IP Fabric limits circular layout to 500 nodes and switches to "universal" above 100 (section 2.7). A
  NetBrain community answer advises at most about 50 devices per map (opinion,
  [forum](https://exchange.netbrain.com/general-46/map-hierarchy-108)), and NetBrain itself drills down
  through a site hierarchy (section 2.9).
- **Grouping keys.** IP Fabric assigns sites by hostname or SNMP-location rules and lets an unmatched
  device inherit its neighbours' site (section 2.7); Forward places devices into locations by glob
  patterns on names (section 2.8); CloudVision by tags (section 2.6). Here, only NetBox-sourced lists have
  a site (section 6).
- **Search.** The only documented map search found is IP Fabric's: typing filters the view to what
  matches, and the Search button focuses and zooms to the item (network viewer, above). No other tool's
  map search behaviour was found in the sources read.

### 4.8 Phone

- **What tools document.** IP Fabric documents pinch to zoom, tap to select and drag for touch as well as
  desktop ([network viewer](https://docs.ipfabric.io/main/IP_Fabric_GUI/diagrams/network_viewer/)). The
  third-party Zabbix module documents "touch + long-press for the context menu"
  ([README](https://github.com/linuser/zabbix-network-topology/blob/main/README.md)). Forward's only
  PeerSpot review asks for "an Android version or desktop" (opinion,
  [PeerSpot](https://www.peerspot.com/products/forward-enterprise-reviews)).
- **What was not found.** No documented phone behaviour for the NetBox plugin, LibreNMS maps or native
  Zabbix maps; SolarWinds, Catalyst Center and CloudVision phone behaviour was not researched
  (section 8).
- **Libraries.** Cytoscape's touch handling is maintained; vis-network's pinch-zoom fails in Firefox on
  Android, open since 2020; d3-zoom handles pinch and double-tap (section 5.2).
- **Already decided here.** P.11: pan and pinch-zoom; below a set width the default is a list of devices
  with their links; path trace is a list of hops (`docs/NSOT_PLAN.md:4282-4288`).

---

## 5. Drawing technology, costed against this stack

### 5.1 The constraints

- **The strict policy.** v2 pages are served under `STRICT_POLICY`: `script-src 'self'`,
  `style-src 'self'` (no `unsafe-inline`, no `unsafe-eval`), `img-src 'self' data: blob:`,
  `connect-src 'self'`, and no `worker-src` or `child-src` (`modules/csp.py:51-67`). Tests assert no
  `style=`, `<style>` or `on…=` in a rendered v2 page (`tests/test_device_v2.py:237-247`).
- **What that blocks.** A `style` attribute, `setAttribute('style', …)` and `style.cssText` are blocked;
  per-property writes such as `el.style.display = …` are not
  ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src)).
  A library that injects a `<style>` element fails. Workers fall back to `script-src`
  ([CSP3](https://www.w3.org/TR/CSP3/)), so a worker from a same-origin file is allowed and a `blob:`
  worker is not.
- **SVG.** SVG presentation attributes (`fill=`, `stroke=`) appear to fall outside `style-src`: the v2
  icons use them under the strict policy (`templates/v2/_macros.html:6`), and the manual's diagram loader
  refuses any SVG carrying `style=` (`modules/manual.py:204-214`). No spec sentence was found saying so
  (inference). Firefox's CSP blocks SMIL `<animate>` of `fill` and `stroke` in inline SVG (open bug
  [1459872](https://bugzilla.mozilla.org/show_bug.cgi?id=1459872)), so an animated down link uses CSS
  animations from the stylesheet.
- **The front end.** htmx with `allowEval` and `allowScriptTags` false and its indicator styles off,
  plus Alpine's CSP build with ES5 components (`templates/v2/base.html:11`, `static/js/nmas_v2.js:1-11`).
  htmx swaps HTML, so an SVG fragment swapped on its own lands in the wrong namespace; wrap it in
  `<template><svg>…</svg></template>` and swap out of band ([hx-swap-oob](https://htmx.org/attributes/hx-swap-oob/)).
  `hx-preserve` keeps a client-side graph container alive while htmx replaces what is around it
  ([hx-preserve](https://htmx.org/attributes/hx-preserve/)).
- **Vendoring.** No build step and no CDN. A library is vendored from its npm tarball with the registry's
  sha512 checked (`scripts/nmas-vendor:1-16`), and `tests/test_csp.py:69-91` requires every vendored file
  to be loaded by one of four named templates, so a library loaded only by a new topology template fails
  until that list changes.
- **Theming.** A canvas or WebGL library colours from JavaScript, so dark mode means reading the CSS tokens
  and redrawing on `nmas:theme`, as the v2 charts already do (`static/js/nmas_panels.js:184-190, 374`).
  Server SVG themed by classes needs neither step.
- **Licence.** The recommended (not yet decided) product licence is Apache-2.0
  (`docs/NSOT_STAGE10_PLAN.md:668-680`), so a library must be compatible with distributing under it. The
  server side already decided is permissive too: NetworkX is 3-clause BSD
  ([LICENSE.txt](https://raw.githubusercontent.com/networkx/networkx/main/LICENSE.txt)), SciPy is
  BSD-3-Clause ([LICENSE.txt](https://raw.githubusercontent.com/scipy/scipy/main/LICENSE.txt)), and NumPy
  declares `BSD-3-Clause AND 0BSD AND MIT AND CC0-1.0`
  ([pyproject.toml](https://raw.githubusercontent.com/numpy/numpy/main/pyproject.toml)), all read
  2026-10-01. Whether those bundled licences are compatible with Apache-2.0 distribution is an inference
  from their being permissive, not a legal review.

### 5.2 The options

No source measures these options side by side at 10, 200 and 2,000 nodes with preset positions on
desktop, wall and phone hardware. A comparison guide also declines to give universal node-count limits
([pkgpulse](https://www.pkgpulse.com/blog/cytoscape-vs-vis-network-vs-sigma-graph-visualization-javascript-2026)).
The performance rows below are therefore the evidence that exists plus labelled inference.

**Server-drawn SVG (htmx), with d3-zoom for pan and zoom**

| | |
|---|---|
| Licence | The app's own code; d3 modules are ISC ([license](https://raw.githubusercontent.com/d3/d3-force/main/LICENSE)) |
| Maintenance | Ours. d3 is mature and rarely released (d3 7.9.0, 2024-03-12, [releases](https://api.github.com/repos/d3/d3/releases?per_page=4)); d3-zoom's latest is 3.0.0, published 2021-06-10 ([npm registry](https://registry.npmjs.org/d3-zoom)) |
| UMD build | d3-zoom ~10 KB raw, plus d3-selection, d3-drag and their dependencies on the global `d3` ([d3-zoom](https://cdn.jsdelivr.net/npm/d3-zoom@3.0.0/dist/d3-zoom.min.js)) |
| CSP | Presentation attributes and classes (inference that they are allowed; precedent in this repo). d3's `.style()` uses `style.setProperty`, which CSP allows ([style.js](https://cdn.jsdelivr.net/npm/d3-selection@3.0.0/src/selection/style.js)). The full d3 bundle has one `new Function` in d3-dsv; vendoring only the needed modules leaves it out ([d3-dsv #87](https://github.com/d3/d3-dsv/pull/87)). `svg-pan-zoom` is not an option: it sets a `style` attribute and injects `<style>`, and is barely maintained ([source](https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.2/dist/svg-pan-zoom.js)) |
| Renderer | SVG in the DOM; each element can carry an accessible `<title>`, which canvas cannot ([MDN](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/title)) |
| Interaction | Click, hover and links are ordinary DOM. Drag-to-pin, path highlighting and collapse are hand-built. Live state updates in place by out-of-band swaps |
| Layout | Any server layout: NetworkX role layers, saved positions |
| Performance | SVG and canvas performed almost equally in a controlled pan/zoom test; frame rate fell above about 400 nodes (about 8,000 elements), and about 10,000 elements is the rough limit for a fluid interface on a 2017 laptop with integrated graphics ([Horak et al. 2018](https://imld.de/cnt/uploads/Horak-2018-Graph-Performance.pdf)). 10 and 200 nodes: comfortable (inference). 2,000 devices at 5-10 elements each reaches or exceeds that limit, so collapse by site or role is required (inference) |
| Phone | d3-zoom handles drag, wheel, pinch and double-tap; touch listeners only where touch exists ([d3-zoom](https://d3js.org/d3-zoom)) |

**Cytoscape.js**

| | |
|---|---|
| Licence | MIT ([LICENSE](https://raw.githubusercontent.com/cytoscape/cytoscape.js/unstable/LICENSE)) |
| Maintenance | Active: v3.34.3 on 2026-09-07, six releases April-September 2026 ([releases](https://api.github.com/repos/cytoscape/cytoscape.js/releases?per_page=6)); mostly one maintainer ([commits](https://api.github.com/repos/cytoscape/cytoscape.js/commits?per_page=25)); 15 open issues and 8 open PRs, with a stale config that marks an issue stale after 14 days and closes it 7 days later, so the low count partly reflects that policy ([stale.yml](https://raw.githubusercontent.com/cytoscape/cytoscape.js/unstable/.github/stale.yml)). Extensions the recommendation relies on: cytoscape-fcose is MIT, last released v2.2.0 on 2023-01-17, repository pushed 2026-04-17, and needs three UMD scripts (layout-base, cose-base, cytoscape-fcose) ([repo](https://api.github.com/repos/iVis-at-Bilkent/cytoscape.js-fcose); [README](https://raw.githubusercontent.com/iVis-at-Bilkent/cytoscape.js-fcose/master/README.md)). cytoscape-elk is MIT, v2.3.0, one open issue, and runs ELK on the main thread when loaded by `<script>` ([repo](https://api.github.com/repos/cytoscape/cytoscape.js-elk); [build](https://cdn.jsdelivr.net/npm/cytoscape-elk@2.3.0/dist/cytoscape-elk.js)) |
| UMD build | `dist/cytoscape.min.js`, no runtime dependencies, 435 KB raw, about 136 KB gzipped |
| CSP | No eval, `new Function`, `setAttribute('style')`, `innerHTML` or `cssText` in 3.34.3. It injects one `<style>` (`position: relative` on its container class) unless an element with id `__________cytoscape_stylesheet` already exists; the app's own stylesheet can carry that rule (inference, untested) ([source](https://cdn.jsdelivr.net/npm/cytoscape@3.34.3/dist/cytoscape.umd.js)). Strict `style-src 'self'` support since 2019 ([PR #2318](https://github.com/cytoscape/cytoscape.js/pull/2318)) |
| Renderer | Canvas; a WebGL renderer in preview (opt-in, no dashed lines, no gradients) ([blog](https://blog.js.cytoscape.org/2025/01/13/webgl-preview/)). Accessibility is the application's job (opinion of the maintainer, [discussion](https://github.com/cytoscape/cytoscape.js/discussions/3125)) |
| Interaction | Pinch-to-zoom, box selection, panning and dragging out of the box; a node can be `locked` or made non-grabbable; the `preset` layout keeps supplied positions ([intro](https://raw.githubusercontent.com/cytoscape/cytoscape.js/unstable/documentation/md/intro.md)). Compound nodes (a `parent` field) group by site; an expand-collapse extension collapses them |
| Layout | Built-in concentric (levels from a role rank), breadthfirst, preset; extensions for ELK, dagre and fCoSE constraints ([extensions](https://raw.githubusercontent.com/cytoscape/cytoscape.js/unstable/documentation/md/extensions.md)) |
| Performance | Maintainers' figures (M1, Chrome): about 1,200 nodes and 16,000 edges at about 20 FPS on canvas and over 100 FPS on WebGL ([blog](https://blog.js.cytoscape.org/2025/01/13/webgl-preview/)). A network topology has far fewer edges per node than that test (inference). One user saw WebGL drop from about 30 to about 5 FPS on integrated graphics ([#3436](https://github.com/cytoscape/cytoscape.js/issues/3436), now closed). Canvas cost grows with screen area; `pixelRatio: 1` is advised on high-density screens, which makes a 4K wall the expensive case ([performance.md](https://raw.githubusercontent.com/cytoscape/cytoscape.js/unstable/documentation/md/performance.md)). A 200-node data point: a user measured about 50 ms of render calculation for 286 nodes and 288 edges in the Chrome profiler, and the maintainer noted an open debugger slows it considerably (opinion, [discussion #3088](https://github.com/cytoscape/cytoscape.js/discussions/3088)). By size (inference): 10 and 200 nodes comfortable on canvas; 2,000 within the canvas figures above for network-like edge counts, with WebGL as headroom |
| Phone | Touch handling maintained: a pinch-to-zoom crash reported 2026-07-20 was patched within days ([#3489](https://github.com/cytoscape/cytoscape.js/issues/3489)) |

**vis-network** (the library P.11 named, and the one vendored for the legacy page)

| | |
|---|---|
| Licence | Apache-2.0 or MIT ([package.json](https://cdn.jsdelivr.net/npm/vis-network@10.1.2/package.json)) |
| Maintenance | 10.1.2 on 2026-08-19 ([releases](https://api.github.com/repos/visjs/vis-network/releases?per_page=8)); of the last 100 commits, 79 by a dependency bot and 20 by one human maintainer ([commits](https://api.github.com/repos/visjs/vis-network/commits?per_page=100)); 323 open issues and 27 open PRs (GitHub search API, read 2026-10-01) |
| UMD build | Standalone (652 KB, CSS included) or peer (412 KB) plus vis-data's peer build (114 KB) and a separate stylesheet |
| CSP | The **standalone** build injects its stylesheet as `<style>` elements; the vendored 9.1.6 is the standalone build (`static/js/vendor/MANIFEST.json`), so its tooltip and navigation styling would be refused under the strict policy. The **peer** build injects none and styles only by per-property writes ([peer build](https://cdn.jsdelivr.net/npm/vis-network@10.1.2/peer/umd/vis-network.min.js)). Both keep a `Function("return this")()` fallback behind `globalThis`, which should never run in a current browser (inference). A 2019 no-eval CSP report is still open ([#271](https://github.com/visjs/vis-network/issues/271)). Its button icons are `data:` PNGs, which `img-src` allows |
| Renderer | Canvas |
| Interaction | Drag, keyboard, navigation buttons; nodes accept `x`/`y`, `fixed` and `physics: false` |
| Layout | Hierarchical layout from a per-node `level` (role), direction UD/DU/LR/RL; Kamada-Kawai initial placement (`improvedLayout`). Above 100 nodes that initial layout clusters internally (`clusterThreshold` 150); this is part of computing the layout, not a visible collapse ([layout](https://visjs.github.io/vis-network/docs/network/layout.html)) |
| Scale | An explicit clustering API is the visible collapse: cluster by a join condition, by connection or by hub size, and reopen with `openCluster` ([docs](https://visjs.github.io/vis-network/docs/network/index.html)) |
| Performance | Docs claim smooth operation "for up to a few thousand nodes and edges" ([docs](https://visjs.github.io/vis-network/docs/network/index.html)). Its physics is slow at scale (force layout took over a minute at 1,000 nodes in a 2022 benchmark, [Memgraph](https://memgraph.com/blog/you-want-a-fast-easy-to-use-and-popular-graph-visualization-tool)), which does not matter with physics off and positions preset. By size (inference): 10 and 200 nodes comfortable with physics off; 2,000 within the docs' claim, unmeasured here |
| Phone | Pinch-zoom fails in Firefox on Android, open since 2020 ([#1057](https://github.com/visjs/vis-network/issues/1057)) |
| Precedent | NetBox's plugin uses it with saved positions; LibreNMS's complaints were about its physics |

**sigma.js (with graphology)**

| | |
|---|---|
| Licence | MIT ([LICENSE.txt](https://raw.githubusercontent.com/jacomyal/sigma.js/main/LICENSE.txt)) |
| Maintenance | Stable 3.0.3; v4 in beta (the last six releases are pre-releases, latest 4.0.0-beta.6 on 2026-09-16), so the API is moving ([releases](https://api.github.com/repos/jacomyal/sigma.js/releases?per_page=6); [dist-tags](https://data.jsdelivr.com/v1/package/npm/sigma)); 8 open issues, 3 open PRs |
| UMD build | `sigma.min.js` 188 KB (global `Sigma`) plus graphology's UMD 74 KB |
| CSP | No eval, no `<style>` injection, per-property styling; a `blob:` URL only to load SVG images, which `img-src` allows ([bundle](https://cdn.jsdelivr.net/npm/sigma@3.0.3/dist/sigma.min.js)). graphology's ForceAtlas2 worker is built from a `blob:` URL, which the policy blocks, and ships no UMD build |
| Renderer | WebGL, aimed at "thousands of nodes and edges"; custom drawing is harder ([site](https://www.sigmajs.org/)) |
| Interaction | Pan and pinch built in; node dragging and pinning are application code ([example](https://raw.githubusercontent.com/jacomyal/sigma.js/main/packages/storybook/stories/2-advanced-usecases/mouse-manipulations/index.ts)) |
| Layout | None of its own; graphology offers force, ForceAtlas2 and noverlap only, nothing layered |
| Performance | Most headroom at 2,000 (WebGL) (inference). No sigma measurement on integrated GPUs was found; the "varies on integrated GPUs" evidence is Cytoscape's WebGL report ([#3436](https://github.com/cytoscape/cytoscape.js/issues/3436)), which may or may not carry over. By size (inference): 10 and 200 nodes trivially within range; WebGL is aimed at "thousands" |
| Wall | By default labels are thinned on a grid and edge labels not drawn, so not every device name shows at once (inference from [settings.ts](https://raw.githubusercontent.com/jacomyal/sigma.js/main/packages/sigma/src/settings.ts)) |
| Stability | `autoRescale` is on by default: a node placed outside the current extent rescales the whole view unless a custom bounding box is set, which the official drag example does (settings.ts above; [example](https://raw.githubusercontent.com/jacomyal/sigma.js/main/packages/storybook/stories/2-advanced-usecases/mouse-manipulations/index.ts)). A hazard for "nothing moves" (inference) |

**d3-force** (a layout engine, not a renderer)

| | |
|---|---|
| Licence | ISC ([LICENSE](https://raw.githubusercontent.com/d3/d3-force/main/LICENSE)) |
| Maintenance | Last release v3.0.0 (2021-06-05); repository last pushed 2023-12-30; 15 open issues, 12 open PRs; mature ([releases](https://api.github.com/repos/d3/d3-force/releases?per_page=4); [repo](https://api.github.com/repos/d3/d3-force)) |
| UMD build | 8 KB, needing d3-quadtree, d3-dispatch and d3-timer on the global |
| CSP | Clean (no eval or style injection in d3-force or d3-zoom) |
| Renderer | None; drawing is the application's code (SVG or canvas) |
| Layout | Force only; `fx`/`fy` pin a node; forceX/forceY can hold role bands; no layered layout ([simulation](https://d3js.org/d3-force/simulation)) |
| Performance | Force convergence in the 2022 benchmark: 0.4 s, 3.2 s, 27 s at 100, 1k, 10k elements ([Memgraph](https://memgraph.com/blog/you-want-a-fast-easy-to-use-and-popular-graph-visualization-tool)); irrelevant with preset positions. Drawing cost at 10, 200 and 2,000 nodes is whatever renderer the application pairs it with (SVG or canvas rows above) |

**ELK.js** (layered layout) and **dagre**

| | |
|---|---|
| Licence | ELK: EPL-2.0 or GPL-3.0-or-later, weak copyleft, unlike every other candidate. Distributing it obliges making its source available; secondary sources read unmodified use in a separate file as imposing nothing on the app's own code ([LICENSE](https://cdn.jsdelivr.net/npm/elkjs@0.12.0/LICENSE.md); [FOSSA](https://fossa.com/blog/open-source-software-licenses-101-eclipse-public-license/)). dagre: MIT |
| Maintenance | ELK active: 0.12.0 on 2026-07-17, repository pushed 2026-09-17, 91 open issues ([releases](https://api.github.com/repos/kieler/elkjs/releases?per_page=6)). dagre 3.1.1 on npm, while GitHub's latest release is v2.0.0 (2025-11-23) ([package.json](https://cdn.jsdelivr.net/npm/@dagrejs/dagre/package.json); [releases](https://api.github.com/repos/dagrejs/dagre/releases?per_page=5)) |
| UMD build | ELK: `elk.bundled.js` 1.6 MB (467 KB gzipped), a global `ELK`; shrinking it has been an open request since 2017. dagre: 49 KB |
| CSP | ELK: no eval, no blob, no style injection; a worker from a same-origin `/static/` URL passes the strict policy. dagre: no eval |
| Layout | ELK partitioning puts lower partitions first in the layout direction (core, then distribution, then access) and lays out nested graphs ([partition](https://eclipse.dev/elk/reference/options/org-eclipse-elk-partitioning-partition.html)) |
| Performance | Seconds well before 2,000 nodes: 406 nodes and 2,301 edges in about 4 s ([#372](https://github.com/kieler/elkjs/issues/372)); about 33 s reported at 1,000 ([report](https://github.com/LanternOps/breeze/issues/7285)). Loaded as the bundle, it runs on the main thread and freezes the page; a real worker needs `elk-api.js` with `workerUrl` |

### 5.3 Recommendation

**Compute placement on the server, save it, and have the browser draw preset positions only.** This is
the one decision every option shares. It removes physics from the page (the dominant complaint in
section 3), makes "nothing moves on refresh" a property of the data rather than of a library, and turns
the performance question into a drawing question. NetworkX's analyses (components, articulation points,
bridges, shortest paths) need no numpy; its layout functions do (`kamada_kawai_layout` needs numpy and
scipy; `spring_layout` needs numpy), and neither is in `requirements.lock`, which is generated on the host
([layout.py](https://raw.githubusercontent.com/networkx/networkx/main/networkx/drawing/layout.py);
`requirements.lock:1-13`). Role-band placement of new devices can probably be written without them
(inference).

**For the interactive page, the leading candidate is Cytoscape.js.** Reasons, in order:

1. It is the only canvas library found with a deliberate, long-standing strict-CSP stance (inference
   from PR #2318 and the trackers searched; sigma 3.0.3, a WebGL library, is clean by inspection but
   states no stance), and its one `<style>` injection can probably be pre-empted (inference, untested).
2. Preset positions, `locked` nodes, compound nodes for sites, an expand-collapse extension and
   maintained touch handling cover "nothing moves", "move and pin", grouping and the phone.
3. MIT, actively released, one UMD file, no dependencies.
4. A WebGL renderer exists for headroom at 2,000 devices, though it is a preview.

Against it: canvas is invisible to screen readers (Zabbix's text summary is a good pattern to copy), and
colours must be fed from the CSS tokens, as the v2 charts already do.

**Server-drawn SVG is the strong alternative, and may be the better wall view (inference).** It is native
to the strict policy, themes by class, carries accessible titles, should be able to update live state by
out-of-band swaps without any client state (inference from the htmx docs, untested), and is what
`deploy/topology/rcn-topology.py` already produces. It costs hand-built
interaction (drag-to-pin, path highlight, collapse), d3-zoom for pan and zoom, and mandatory collapse at
2,000 devices.

**vis-network, as P.11 named it, should be re-opened in the spike, not assumed.** The vendored file is
the standalone build, which the strict policy will partly refuse; the peer build plus its stylesheet would
fix that. Its Firefox Android pinch bug has been open since 2020, and it is maintained mostly by
automation and one person.

**Not recommended:** sigma.js (v4 API in flux, no layouts, dragging is app code, labels thinned by
default) and d3-force as a renderer. ELK only if server placement proves not good enough, after a licence
review; dagre (MIT, 49 KB) is the lighter layered alternative.

**The deciding test is a spike with the real lab data, which the operator judges on how it feels on a
desktop, a wall display and a phone.** This section narrows the field; it does not decide it.

### 5.4 What the spike should compare

- **Candidates.** (A) server SVG with d3-zoom; (B) Cytoscape.js on canvas; (C) vis-network peer build.
  Optionally Cytoscape's WebGL renderer at 2,000 nodes.
- **Same input for all.** The graph from the real Prometheus capture
  (`tests/fixtures/topology/lldpRemEntry.json`, `up.json`) plus the routing adjacencies from
  `modules/neighbours.py`; and synthetic graphs at 200 and 2,000 devices. The scale fixture has no links
  today (`tests/fixtures/fleet_scale.py:1-40`), so the spike needs a link generator.
- **Same positions for all,** computed on the server, so only drawing differs.
- **Measured, not felt:** time to first draw; pan and zoom frame rate; the number of CSP violation reports
  under `STRICT_POLICY` (zero, or each explained); bytes loaded; whether a link-state change lands with no
  node moving; whether drag-to-pin survives a refresh exactly; dark/light switch; label size in arc minutes
  at the wall's real viewing distance.
- **Felt, by the operator:** the desktop page; the wall display in kiosk form; the phone, with pinch, pan
  and tap tried on Firefox for Android and iOS Safari; a path highlighted; a site collapsed and expanded.
- **On the real wall player's browser.** A practitioner warns that Raspberry Pi players usually run an
  older Chromium on which modern front-end code may fail (opinion,
  [Hacker News](https://news.ycombinator.com/item?id=30870661)), so each candidate is tried on the actual
  device that will drive the wall, not only on a desktop browser at wall size.
- **A text equivalent for the canvas option.** Check that a canvas candidate can carry a summary a screen
  reader reads, in the manner of Zabbix's map summary ("1 of 6 elements in problem state ...",
  [monitoring maps](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/monitoring/maps)),
  since canvas content is invisible to assistive technology
  ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/canvas)).

---

## 6. What this repository already has

**Two topology implementations, which P.11 must reduce to one.**

- `modules/topology.py:1-12` is the legacy discovery: it queries every online device over SSH per request
  (CDP/LLDP, then OSPF, BGP and running-config for the protocol views) and feeds the legacy vis.js page.
  Its "Hub/Spoke" labels are DMVPN roles from config, not a layout role (`:610-612`).
  - Its LLDP/CDP builder collapses both ends' reports into one edge and records neither the protocol nor
    the reporting end (`:339-347`, `:377-387`).
  - Its OSPF builder **suppresses** an adjacency only one side reports when both are managed and both
    returned OSPF data, the opposite of "one end = flagged" (`:908-918`).
  - Retiring it has non-UI consumers: the pipeline imports `parse_bgp_summary`, the one BGP reader
    (`modules/pipeline.py:2221`); `/configure/interfaces` imports `parse_ip_interfaces` (`app.py:89`); and
    the agent's `get_network_topology` and `GET /ai/topology_context` run discovery on a cache miss
    (`modules/ai_assistant.py:3467-3486`, `app.py:3038-3060`).
- `deploy/topology/rcn-topology.py` is a separate service (port 8088) that reads Prometheus (`up`,
  `sysName`, `lldpRemEntry`, `lldpRemPortId`), uses NetworkX for layout only, and serves an SVG, a page and
  `graph.json` (`:1-36`, `:73-151`, `:342-399`). The app shows the SVG as an `<img>`
  (`routes/topology_view.py:1-22`).
  - One edge per device pair, the first reporter's ports winning; parallel links collapse (`:117-129`).
  - Live state is node reachability only, and a link red-dashed when either node is down (`:249-253`).
  - Layout recomputed every 15 s build, nothing saved (`:53`, `:199-208`). Islands (every component but
    the largest) are placed in a band with a reason (`:182-193`), a rule P.11 inherits.
  - Its `/` page is in effect a kiosk view (dark, full viewport, 30 s refresh) (`:361-377`), and its SVG is
    public with no login (C231, `docs/OPEN_FINDINGS.md:304`).
  - It carries lab-specific defaults (`DEVICE_JOBS` default, the page title, a hostname example) that the
    Stage 10 check's pattern does not match, and the file is not in its inventory (`:49`, `:81`, `:363`;
    `tests/test_lab_specifics.py:34-35`). `modules/host_steps.py:75-89` hard-codes its install path.

**The legacy page's layout handling.**

- The client runs vis.Network with physics off; a node with no saved position is placed by vis's default
  initial layout, not by role; positions are saved only on drag end (`static/js/gen/index.3.js:283-313`,
  `:526`).
- Positions are saved per list and shared, but discovery skips devices offline in the status cache and
  `/topology_data` then prunes the saved positions of every node it did not see, so a device that is down
  for one discovery loses its pin (`modules/topology.py:1202-1208`; `app.py:1911-1930`).
- Saving positions is an ungated `not_device` write ("layout") that stores whatever JSON the client posts,
  with no record of who moved what (`modules/route_gates.py:221-224`; `app.py:1981-1993`).
- Live link state is an SSH poll of `show ip interface brief` on every device in the cached topology each
  time the client timer fires: per-device work per request, against the scale rule (`app.py:2011-2089`).
- The topology cache stores `fetched_at` but `/topology/state` does not return it, so the map is drawn with
  no age; the cache file is written by truncating in place (`modules/ai_assistant.py:1297-1318`).

**Data P.11 can read without new collection.**

- Every scrape target is generated from the inventory and labelled `device` and `role`, with an "all"
  file for the fleet-wide LLDP job and routing files from committed goldens
  (`modules/prometheus_targets.py:1-25`, `:42-53`).
- Scrape intervals bound freshness: switches and OSPF 60 s (slowed to protect the management gateway,
  C93), LLDP 60 s, routers and BGP 30 s (`docs/PROMETHEUS_TARGETS.md:150-171`).
- LLDP series name the remote by System Name only (two different domains in this lab) and the local port by
  `lldpLocPortDesc`/`lldpLocPortNum`, with no `ifIndex` label; interface series carry `ifIndex`, `ifName`
  and `ifAlias`. So joining a link to its counters goes through the port name or `lldpLocPortNum`, which
  equals `ifIndex` on the sampled IOS-XE rows only (`tests/fixtures/topology/lldpRemEntry.json`;
  `tests/fixtures/grafana/dsquery/state.json`). P.11's "joined by ifIndex" (`docs/NSOT_PLAN.md:4264`)
  presumes a label LLDP does not carry.
- Utilisation, errors and discards are already queried by the device dashboard, telemetry first where a
  device streams (`deploy/grafana/build_nmas_device.py:18-20`). `ifHighSpeed`, which P.11 lists for speed,
  appears nowhere in the repository except the plan.
- The `lldp` and `if_mib` exporter modules are not versioned here; only the routing modules are
  (`deploy/snmp_exporter/generator.yml:17-45`).
- Routing layers already exist without device sessions: expected OSPF, OSPFv3 and BGP adjacencies from
  committed intent in two git reads, compared with Prometheus, each row up, down, not_seen or unexpected,
  and "not measured" kept apart from "no neighbours" (`modules/neighbours.py:1-25`, `:305-371`). Its
  comparison grows roughly with the square of the device count and has not been measured at scale
  (`:217-238`, inference).
- The fleet adjacency reader keys a link by its pair and raises after two consecutive reads, but stores only
  failing links; the up adjacencies a layer needs are computed and discarded
  (`modules/readers/adjacencies.py:86-131`).
- Alarms from Needs attention rows (`level`, `devices`) and answering state from the reachability reader
  (5 s probes) (`modules/attention.py:134-136`; `modules/readers/reachability.py:45-49`).

**NetBox cables.**

- The import get-or-creates cables from live CDP/LLDP reads (`modules/netbox_client.py:3103-3127`), and
  register C100 records that the existing cables were made under the operator's account, which is also
  the tool's token, so their origin cannot be told apart. `_ensure_cable` returns any existing cable on
  either interface without checking its far end, so a re-cabled link is never corrected (`:900-929`).
- No code reads cables for comparison; `_nb_get` follows pagination for a fleet-wide read
  (`modules/netbox_client.py:180-200`).
- Retired r5 still has two cables to r3 and r4 and is still their LLDP neighbour: a ready "not managed"
  case (`docs/OPEN_FINDINGS.md:306`).

**Grouping and roles.**

- Roles are `router`, `switch`, `firewall` or empty; no tier exists (`modules/inventory_edit.py:36-39`;
  `modules/inventory/netbox_source.py:26`). The scale fixture invents four tiered roles the product cannot
  hold (`tests/fixtures/fleet_scale.py:34`).
- Site exists only for NetBox-sourced lists; a local CSV list has none (`modules/device.py:37-38`).

**Patterns to reuse.**

- The reader job: one background read, last good value with its time, liveness row, announcement
  (`modules/reader_job.py:1-60`). It keeps no history, so time travel needs a new snapshot store.
- uPlot: an IIFE canvas library plus a separate vendored stylesheet, colours from tokens, redrawn on
  `nmas:theme` (`templates/v2/base.html:16, 20`; `static/js/nmas_panels.js:180-195`).
- Light and dark token sets and breakpoints at 860, 640 and 480 px; panels refresh every 30 s only while
  the page is visible (`static/css/nmas-v2.css`; `static/js/nmas_panels.js:343-355`).

**Plans and documents.**

- P.11 already decides one 60 s reader, NetworkX analyses on the server, vis-network with positions pinned
  by node id, the inventory as the population, and both older implementations retired
  (`docs/NSOT_PLAN.md:4208-4296`). It decides phone behaviour: pan and pinch-zoom, a list form below a set
  width, path trace as a list of hops (`:4282-4288`). Its what-if names the lab's manager attachment point
  (`:4274-4276`), which a network-agnostic design must take from configuration.
- The GUI brief contradicts itself: lines 246, 399, 461 and 1497 still place Topology under Devices
  (line 246 as a Devices tab, the others as "Devices > Topology"), while 1070 and the superseding note at
  1317 make Topology its own OBSERVE page (`docs/NSOT_GUI_BRIEF.md`, line numbers as read on 2026-10-01;
  the brief grew during this research, so an earlier reading had 1469, 1042 and 1289). It fixes
  acceptance questions 33-37 and the one-map rule (`:1317-1331`, `:1799-1805`), and its option (b)
  content is inherited (from `:1350`).
- Older positions remain in the documents: "No fleet view now ... 200 devices is a picture nobody reads"
  (`docs/NSOT_FEATURE_AUDIT.md:42`) and "the destination is the Grafana view"
  (`docs/NSOT_STAGE7_GUI.md:662-680`).
- A v2 screen is not done until its manual page and info link exist; `manual.SCREENS` has no Topology entry
  (`modules/manual.py:72-76`). The cutover lists the legacy topology routes for removal in 7.8 and the
  service's routes as planned under P.11 (`docs/CUTOVER.md:86-87`).
- The data key `topology` already means "the topology layout" (four legacy routes announce it), while P.11's
  reader plans to announce `topology` for the graph; the v2 client relays no topology key
  (`modules/invalidation.py:87`, `:234-237`; `static/js/nmas_v2.js:17-24`).

**Findings for the register** (recorded here because this research may write only this file). The
register, `docs/OPEN_FINDINGS.md`, was searched on 2026-10-01 for each; the outcome is given per item.

- The legacy map's node icons load from `img.icons8.com`, which the legacy page's own CSP refuses, so they
  cannot render; the C123 test scans only `<script src>` and `<link href>` in templates and cannot see a
  URL in a script (`static/js/gen/index.3.js:277-281`; `modules/csp.py:41`; `tests/test_csp.py:19-32`).
  Inference, not observed in a browser. Register search: "icons8" matches nothing; new.
- The legacy click panel writes a node's title with `innerHTML`, and that title embeds a neighbour's
  device-announced CDP/LLDP name unescaped; the hidden-devices list does the same
  (`modules/topology.py:324-334`; `static/js/gen/index.3.js:500-503`, `:91`). Not exploited or tested.
  Register search: "innerHTML" matches only C88 (Save All's and Auto-Create's result toasts, the same
  class at different sites); "LLDP name", "neighbour name" and "System Name" match nothing. New as a site;
  it could extend C88.
- The topology service's lab defaults escape the Stage 10 check (above). Register search: C336 records
  the same pattern gap (`rcn-lab`/`rcn_lab` only) for the break-glass file names; nothing names the
  topology service's defaults ("RCN Lab" matches nothing). It could extend C336. C256 (closed) brought the
  service into the repository and is about its source, not its defaults.
- **Plan and brief statements the research found false or presuming** (documents asserting something the
  code or data does not have):
  - P.11 says the page draws with vis-network "already vendored and hash-pinned"
    (`docs/NSOT_PLAN.md:4246`). It is vendored and hash-pinned, but as the standalone build, which the
    strict policy partly refuses (section 5.2). Register search: "already vendored" and "standalone"
    match nothing relevant (the one "standalone" hit is C97's timing probe); C126 and D8 are about the
    vendored vis-network's origin and an unconfigured service, not its build. New.
  - P.11 joins link facts "by `ifIndex`" (`docs/NSOT_PLAN.md:4264`), a label LLDP series do not carry
    (section 6, data). Register search: "ifIndex" matches nothing; new.
  - P.11 lists `ifHighSpeed` for link speed (`docs/NSOT_PLAN.md:4231`, `:4264`), which nothing in the
    repository reads. Register search: "ifHighSpeed" matches nothing; new.
  - The GUI brief's "Devices > Topology" lines (above). Register search: "Devices > Topology" matches
    nothing; new.

---

## 7. Open questions for the brief

1. **Positions.** Shared by everyone, or a shared layer plus a personal one (as the Zabbix module does)?
   Who may move and pin, and is a move a recorded act with a person behind it? Today it is an ungated
   write.
2. **New devices.** How does a device enter a saved layout without moving anything else: a slot in its
   role band, beside its neighbours with all others fixed, or held in a "new" tray until a person places it?
3. **Role tiers.** The product has router, switch and firewall only. Is a tier (core, distribution,
   access) needed for layered placement, and where does it come from (NetBox role, a new field, the
   graph)?
4. **One-sided links.** Classify by "far end not polled" versus "both polled", and then compare with a
   measured baseline per link, or with per-platform knowledge of which ends do not report? What counts as
   "recently" for fading, given 60 s LLDP scrapes and a 120 s LLDP TTL?
5. **Accuracy test.** NetBox cables may derive from LLDP here. What independent expectation does the
   accuracy test use: committed intent, a hand-kept fixture of the real cabling, or both?
6. **Parallel links and LAGs.** One line with a count (Forward, IP Fabric), or several lines? The SPOF
   analysis needs a `MultiGraph` either way.
7. **Live link state.** Which source wins per link, which end's counters, and where does link speed come
   from, since `ifHighSpeed` is not read anywhere? How is "down" made unmistakable without colour alone?
8. **Path trace.** Graph shortest paths (all equal ones), or routing-table data? The page must say which
   claim it makes.
9. **What-if.** The manager's attachment point as configuration, not a lab value; likewise any baseline
   of expected one-sided links (section 4.3), which must be measured per network, never seeded from this
   lab's device names. What does a "no single point of failure" result say it could not see (shared
   conduits, protocols)?
10. **Wall mode.** Identity through an Access service token, read-only, refresh rate tied to data age,
    label size from viewing distance, and dark versus the light-grey normal state of ISA-101. Rotation or
    a single fixed view?
11. **Time travel.** A snapshot store per change: where, how long, and how a diff is drawn (staged removals
    then additions, or small multiples)? How does it tell "not read" from "gone"?
12. **Scale.** Grouping for local lists, which have no site. Collapse to a summary node with counts.
13. **Retirement.** Which of the two implementations survives, and what replaces `parse_bgp_summary`'s home
    and the agent's topology tool?
14. **Vocabulary.** A new invalidation key for the graph, or redefine `topology`.
15. **Dependencies.** NetworkX (and, for layout, numpy and scipy) through a host-side lock regeneration; an
    ELK licence review if ELK is considered.
16. **Untrusted text.** Every device-announced name escaped, with a test that plants markup.
17. **Documents.** Fix the brief's "Devices > Topology" lines, and write the manual page with the screen.
18. **Layers: overlaid or switched?** Forward switches views from a selector and can add physical links
    under L3 and OSPF (section 2.8); Catalyst Center filters and highlights (section 2.5). Can LLDP, OSPF
    and BGP be shown together, and how is a link with several witnesses drawn?
19. **Search.** What does search match (name, address, site, role, interface), and does it filter the
    view or zoom to the item, as IP Fabric's does (section 4.7)?
20. **Device alarms on a node.** How Needs attention rows appear: severity, an acknowledged state
    (Zabbix's green ring), ownership (the big-board design's red and yellow flags) (section 4.6)?
21. **"Changed recently" on the live map.** A time-limited marker like Zabbix's 30 minutes, and what
    counts as a change (a link appearing or going, a state flip, a moved position)?

---

## 8. Could not verify; looked for and not found

### Unverifiable claims (12), excluded from the sections above

- **SolarWinds auto-connections "all or nothing"** (vendor stream): one reader could fetch the thread and
  one could not. The vendor stream's checker got "Page Not Found" through the reader service; the themes
  stream's checker read the same thread and quoted it verbatim. Section 3 uses the themes stream's
  confirmed reading, but the conflict is not resolved: the page may have been reachable only at one
  moment or through one path.
- **IP Fabric "Dynamic Diagrams part 2: Persistence"** blog, reported to say a saved layout survives
  every rediscovery: the URL now serves an unrelated article.
- **IP Fabric release 2.2.5** inferred "MAC edges" and per-protocol tooltips: the blog URL redirects to the
  release index.
- **IP Fabric Gartner Peer Insights praise** for automatic maps: HTTP 403.
- **Forward G2 reviews** calling the UI heavy and slow: HTTP 403.
- **NetBrain EE 6.1 help** saying auto layout clears manual adjustments: the page redirect-loops; only
  search-index text, about ten years old.
- **NetBrain TrustRadius reviews** on map slowness and dual SD-WAN links shown as one: HTTP 403.
- **Auvik full wire legend** and **Auvik large-display session advice** (analysis stream): the support
  site returned 403. The themes stream confirmed both from an archived copy; sections 2.10 and 4.1 use that.
- **"Extremes are better"** (Diagrams 2008): only the title was confirmed; the finding that no or maximum
  stability beat medium stability was not.
- **SolarWinds "red dashed line"** meaning the topology calculator could not confirm a drawn connection:
  only a search excerpt of a client-side page; a forum question about it went unanswered.
- **A human-centred study of a NOC** (SIW 2014), reported to find shift managers struggle to build one
  mission-level picture: the paper was not reachable.

Also excluded: a reseller blog asserting NetBrain cannot trace paths across VRFs, which cites no evidence,
and a press quote about CloudVision path tracing whose URL was not given.

### Looked for and not found

- **Opinion sources.** Reddit (r/networking, r/sysadmin, r/zabbix, r/netbox) refused every fetch; G2,
  Gartner and TrustRadius returned 403; the Zabbix forum returned 403 or a challenge.
- **Disagreement on the map.** No product draws documented cabling against discovered LLDP as findings
  (only a zero-star CLI and the override mechanisms in Forward and IP Fabric); none draws both-ends against
  one-end sightings; none shows a link's "last seen" age or fades stale links. None compares routing
  adjacencies (OSPF, BGP) with LLDP links on the map; SuzieQ's per-source columns are the nearest model,
  and they are a table, not a drawing.
- **Phone behaviour of the tools.** Not researched for SolarWinds, Catalyst Center or CloudVision (the
  vendor stream's scope did not list it). No documented phone or touch behaviour was found for the
  NetBox plugin, LibreNMS maps or native Zabbix maps. Forward's only PeerSpot review asks for an Android
  app (section 4.8).
- **Search** behaviour on any map other than IP Fabric's (section 4.7).
- **Wall modes.** None for Catalyst Center, CloudVision or NetBrain topology; no HCI evidence on dark versus
  light themes for wall displays; ISO 11064 and the ISA-101 text itself (paywalled) not read.
- **Persistence details.** Whether Forward's saved layouts survive snapshots; how IP Fabric places a new
  device into a saved layout; whether CloudVision allows drag-to-place; whether LibreNMS's network map saves
  positions (no save endpoint exists).
- **What-if and SPOF** in SolarWinds, Catalyst Center, CloudVision, NetBrain and Forward.
- **Map time travel** in Catalyst Center and CloudVision's topology help.
- **Drawing.** No side-by-side benchmark of the candidates with preset positions; no phone performance
  measurements; no measurement of sigma.js on integrated GPUs; no specification text on SVG presentation attributes and `style-src`; no CSP issue in the
  elkjs or sigma.js trackers; whether Cytoscape's WebGL renderer has left preview; built-in keyboard and
  screen-reader support in any canvas library; a UMD build of graphology's ForceAtlas2; a Python-side ELK.
- **This repository.** No Topology mockup; no kiosk mode anywhere in the v2 app; no code reading NetBox
  cables for comparison; no versioned `lldp` or `if_mib` exporter module; no `ifHighSpeed` query; no
  topology history store; no link generator in the scale fixture; NetworkX absent from the lock and the
  laptop (the host's version is a claim in `docs/NSOT_PLAN.md:4253`, not checked); no site for local lists;
  no tier vocabulary; no source for the brief's line that Meraki and Catalyst Center give topology its own
  page (Catalyst Center confirmed here; Meraki not researched).
