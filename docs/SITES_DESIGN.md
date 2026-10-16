# Sites: several sites in one network, and a read-only view across networks (design)

**FUTURE, post-cutover: not Phase 7 work, and nothing here is built.** The operator's request,
2026-10-16. This is a general capability: any single Mercury instance managing several sites,
headquarters' own management network included (a campus, a data centre and its branch offices
as sites of one network, managed by one instance). It is **not** the design for the fly-away kit
fleet. By the operator's decision of 2026-10-16, each kit is its own network on its own Mercury
instance, under a headquarters manager; that fleet is designed in
[EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md). Material from the satellite case stays here only
where it applies to one instance managing several sites (section 10). The governing definition
is [MERCURY_CHARTER](MERCURY_CHARTER.md): NetBox owns a device's existence, identity, role, site,
platform and status, and Mercury reads them. The ownership of every piece of device state is in
[NSOT_OWNERSHIP](NSOT_OWNERSHIP.md). The sibling notes, written the same day, are
[FLOWS_DESIGN.md](FLOWS_DESIGN.md), [IPAM_IMPORT_DESIGN.md](IPAM_IMPORT_DESIGN.md) and
[BRINGUP_FROM_DOCUMENTS.md](BRINGUP_FROM_DOCUMENTS.md); the order is sites first, then flows and
the IPAM import's site and VRF mapping.

## 1. The shape, in one paragraph

A **network** stays what it is today: one inventory, one configuration repository, one set of
credentials and records, the unit every write is inside. Within it, **site becomes a per-device
attribute**. In NetBox a network maps to a Region (or a Tenant, section 3), and each device sits
in its own site beneath it. A device with no site is in the site named after its network, which is
exactly the one site the import makes today, so Default needs no migration. **Site membership has
one owner per network:** NetBox for a NetBox-sourced network, Mercury's committed record for a
local one. Where identical sites repeat their addressing, each such site gets its own VRF (or its
prefixes are scoped to the site). Prometheus targets gain a `site` label, so Grafana, alert rules
and Loki filter by site with no NetBox plugin. The Devices, Topology and Needs attention screens
group by site, with no extra level for a network that has one site. Across networks there is no
merged device list. Instead there is a **read-only All-networks scope: read across, write within.**

## 2. Today, read in the code

### How a network becomes NetBox objects

`modules/netbox_client.py`, `_sync_list_to_netbox_impl`, runs once per network import:

| Object | Function | What it does today |
|---|---|---|
| Region | `_ensure_region(session, base, list_name)` | get-or-create by slug, named after the network |
| Site | `_ensure_site(session, base, list_name, region["id"], notes=...)` | one site, the network's name, under that region. It re-parents an existing site only when Mercury created it (`netbox_guard.has_managed_tag` OR `netbox_guard.was_created_by_nmas`). Otherwise it leaves the site where a person put it and says so in `provisioning_notes` |
| VRF | `_ensure_vrf(session, base, list_name, rd=f"ndm:{_slug(list_name)}")` | one "list VRF" per network, looked up by name alone; an interface with its own `vrf_name` takes that VRF instead |
| Device | `_upsert_device(..., site_id=site["id"], ...)` | every device of the network goes into that one site |
| VLAN | `_ensure_vlan(session, base, vid, name, site_id)` | looked up and created per site |
| Prefix | `_ensure_prefix(..., site_id=..., vrf_id=...)` | looked up by prefix and VRF; `site` is sent on create |

Three properties of today's code that this design keeps:

- **Site is create-only on a device.** `_upsert_device`'s update allowlist is `name`, `serial`,
  `comments`, `local_context_data`, `config_template` and `custom_fields`. A device's site, like
  its status, platform, type and role, is never rewritten by a later import. So a person's
  placement of a device in NetBox already survives the sync.
- **Mercury never moves a site it did not create** (`_ensure_site`'s docstring gives the
  reasoning: tagged OR recorded to re-parent, tagged AND recorded to delete).
- **Removal deletes only what is tagged AND recorded** (`remove_list_from_netbox`;
  `modules/netbox_guard.py`, `MANAGED_TAG`, `record_created`, `get_created`,
  `recorded_objects`). The created-id record is kept per network, not per site.

One property this design must change (section 3): `_existing_device(session, base, hostname,
site_id, serial)` matches by serial only when the serial is unique, and otherwise by **name
within the network's one site** (`_nb_first(..., name=hostname, site_id=site_id)`). A device that
a person moved to another site in NetBox, and whose serial is shared or unreadable, is therefore
not found, and the next import would create a second record of that name in the network's site.
Whether this happens today is UNKNOWN; measurement M1 settles it. Onboarding from a Planned
record avoids it, because it passes `netbox_id` and `_record_by_id` updates that record.

### Where site already appears

- **A NetBox-sourced network can already be filtered by site.** `modules/network_source.py`,
  `FILTERS = ("site", "role", "tag", "status")`; `proposal()` refuses a NetBox network with no
  filter. `modules/inventory/netbox_source.py`, `fetch_netbox_devices`, passes each filter to
  `dcim/devices/`; `adapt_devices` carries each device's site slug as `_site` (presentation-only
  metadata, never sent to a device).
- **Credentials already resolve by site.** `modules/credentials.py`, `resolve(mgmt_ip, role,
  site, credential_list)`: device override, then the designated list, then `role:<role>`, then
  `site:<site>`, then the default profile. `adapt_devices` passes `site=site_slug`.
- **Templates already see the device's site.** `modules/nsot/context.py`,
  `build_render_context`, reads the device's NetBox site record into `context["site"]`; the
  pipeline calls it (`modules/pipeline.py`).
- **A local network has no site.** `modules/device.py`, `DEVICE_CSV_FIELDS` is `hostname,
  device_type, ip, username, password, secret, role, device_uid, platform`.

### Where site is absent

- **Prometheus targets** (`modules/prometheus_targets.py`, `generate`): each group's labels are
  `{"device": host}` plus `role` when the inventory has one. No site, and no network.
- **The Devices list** (`modules/device_list.py`, `listing(ref, ...)`): one network's rows, filtered
  by name or address, intent state and platform. No site, no grouping. The large-fleet rule names
  it as a gap (`tests/test_large_fleets.py`, `EXCUSED["/v2/devices"]`: "7.4's revised Devices
  board (summary, groups, paging) is owed (C450)").
- **Topology** (`modules/topology_page.py`, `view(list_name, values)`): one network's map from the
  topology reader's stored value (`modules/readers/topology_graph.py`, one graph per network). The
  phone's device list groups by device class (`_list_groups`). A network of more than
  `COLLAPSE_ABOVE` (150) managed devices is drawn collapsed.
- **Needs attention** (`modules/attention.py`, `needs_attention`): already installation-wide.
  Every source's rows are merged, and `_with_networks` (C493) gives each row naming a device a
  `networks` map, from the row's stated network (`_stated_network`) or from every network's
  inventory (`_device_networks`). A row about one network gets `list=` on its action.
  `templates/v2/_attention.html` draws "device (network)" in the row's meta line. There is no
  site, and no Network column.

### What is keyed by address across the whole installation

Several stores are keyed by management address alone, for every network at once. Repeated
addressing therefore has a hard limit inside one instance (section 5):

- `modules/readers/reachability.py`: one probe per address across every registered list ("a
  device on two lists is probed once"); its value is `{address: ...}`, which
  `device_list._status(reach, ip)` reads.
- `modules/credentials.py`: `device_overrides` keyed by management address (`set_device_override`
  refuses an empty key).
- `modules/prometheus_targets.py`, `generate`: an address two devices hold is refused, and
  "neither is scraped under it until one address is one device".
- `modules/nsot/blast_radius.py`: the graph's nodes are `ipaddress.ip_network` values from
  committed intent (`_attachments`), so two sites using the same subnet would be one node.
  `modules/readers/topology_graph.py`, `_iface_networks`, has the same shape.

## 3. The model: a network is a Region (or a Tenant), and site is per device

**The change to `modules/netbox_client.py`:**

1. `_ensure_region` stays: the network's region, named after it. This is today's object.
2. `_ensure_site` is called **once per distinct site the network's devices name**, each under
   the network's region. Its ownership rule is unchanged (tagged OR recorded to re-parent).
3. **A device with no site is in the site named after its network.** For Default and for
   every network today, that is exactly the site the import already made, so nothing moves and
   there is no migration.
4. `_upsert_device` receives the device's own site id. On create it is the device's site. On
   update, site stays outside the allowlist, so a person's placement in NetBox survives.
5. `_existing_device`'s name fallback is scoped to the **network's region**, not to one site
   (NetBox's device filter `region_id`), and a device whose manifest entry is `nb:<id>`
   (`modules/nsot/manifest.py`) is updated by that id, as `_record_by_id` already does for
   onboarding. This closes the duplicate described in section 2. Whether NetBox's region filter
   includes child regions on the installed version is measurement M3.
6. `_ensure_vlan` already takes a site, so VLANs become per device site with no new code.
7. Prefixes: section 5.

**Region or Tenant.** A Region is NetBox's geographic hierarchy: a site has exactly one, and a
region can nest. A Tenant is ownership, independent of geography, and can be set on sites,
devices, prefixes and VRFs. **Recommendation: Region by default**, because it is the object the
import already makes (no migration), and a network's sites can sit in child regions beneath it
(headquarters, then East and West). **A network declares Tenant instead** where its NetBox
already uses regions for geography that crosses networks. The declaration names why a
measurement could not answer it: whether an installation's regions are already geographic is a
fact about how people use NetBox, not something Mercury can measure.

**The NetBox-sourced network's filter gains `region` and `tenant`.** `network_source.FILTERS`
and `netbox_source.fetch_netbox_devices` add the two keys beside `site`, `role`, `tag` and
`status`. The approved default stays a tag (NSOT_OWNERSHIP Part 2, decision 4). A network that
is a region simply filters by it.

**Site in the render context.** `nsot/context.build_render_context` already reads the device's
site record, so templates may branch on `site.slug` with no change. A site's intent (its NTP or
syslog servers, its management prefix) belongs in NetBox's config context for that site, which
`_fetch_full_device` already requests with `include=config_context`.

## 4. One owner of site membership per network

| Network's source | Owner of a device's site | How it changes | Mercury |
|---|---|---|---|
| NetBox (`source: netbox`) | **NetBox**: the device's `site` | a person in NetBox, or a confirmed Mercury operation through the write chokepoints | reads it (`adapt_devices`' `_site`). Never writes it on update; the next inventory read shows it with its age |
| Local (`source: local`, the declared exception) | **Mercury's committed record**: a `site` field on the device's entry in `config_repo/.nsot/manifest.json` (the one tracked file under `.nsot`, `nsot/repo.MANIFEST_REL`) | a confirmed operation that commits the manifest (preview, confirm by a verified person, `repo.commit`, record) | reads it; absent means the network's own name |

- **Never both.** A local network's site is not copied into NetBox's device record on update
  (create only, as today). A network switching to NetBox (NSOT_OWNERSHIP Part 2's census)
  compares each device's site as well as its name and management address, and refuses the
  switch, naming each mismatch, until they agree.
- **Why the manifest and not `devices.csv`:** the CSV holds credentials and is not committed. The
  manifest is the network's committed identity map, keyed by stable identity (`uid:` or `nb:`),
  so a rename does not lose a device's site, and History shows who moved a device and when.
- **Why not `host_vars/`:** site is identity and placement, not configuration intent. Putting it
  in intent would make a site move look like a configuration change to the deploy path.

## 5. Addressing that repeats: a VRF per site, or site-scoped prefixes

**When it arises.** Several sites of one network are built from one template and reuse their
LAN addressing: every branch's user LAN is 192.0.2.0/25, and every branch's voice LAN is
192.0.2.128/26. (Identical fly-away kits are separate networks on separate instances and do not
meet in one NetBox network: [EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md).)

**In NetBox.** One prefix appearing at several sites needs either:

- **a VRF per site** that repeats addressing, named `<network> / <site>` with RD
  `ndm:<network-slug>:<site-slug>`, made by `_ensure_vrf` as today's list VRF is (get-or-create
  by name, tagged and recorded by `_nb_post`). An interface with no VRF of its own takes **its
  site's** VRF instead of the network's; or
- **site-scoped prefixes** in the network's VRF, where that VRF does not enforce uniqueness.

**Recommendation:** a VRF per site, created only for a site the network declares as repeating
its addressing, because it states the fact that matters (these addresses are separate routing
domains). Every other site keeps the network's VRF, as today. Which of the two NetBox accepts
without changing its uniqueness settings is measurement M4. Section 2 also notes that
`_ensure_prefix` sends `site` on create. NetBox 4.2 replaced a prefix's site with a generic scope
(`scope_type`, `scope_id`), so whether that field lands on the installed NetBox is measurement M2.

**In Mercury, management addresses stay unique per instance.** Reachability, device credential
overrides, Prometheus targets and the instance's own routing table are keyed by address across
every network (section 2). Repeated addressing is therefore supported **off the management
path only**:

- Onboarding and adopt refuse a management address another device already holds in any network
  on this instance, naming both devices and both networks. A refusal names the comparison and
  both operands.
- A site's repeated LAN prefixes are modelled in NetBox and in intent. Mercury never reaches a
  device through them.

**Reach analysis stays conservative.** `blast_radius._attachments` and `topology_graph._iface_networks`
key subnets by value. A subnet that committed intent places at two sites would join them into
one node, so the analysis would report reach that does not exist: optimistic, which
`blast_radius`'s docstring forbids. Until subnets are qualified by site, a radius that touches a
subnet held at two sites answers `unknown` and names the subnet and both sites, never `known`.

## 6. NetBox ownership: unchanged

The existing rules apply to every per-site object exactly as they apply to today's one site:

- **Create:** only through `_nb_post`, which tags `nmas-managed` and records the id against the
  network (`netbox_guard.record_created`). Each site object a network creates is that network's
  created object.
- **Adopt by slug, never move:** a site with a matching slug is used, not duplicated. One that
  Mercury did not create is never re-parented (`_ensure_site`).
- **Update:** records its before (`netbox_guard.record_modified`). A device's site is never on
  the update allowlist.
- **Delete:** only what is tagged AND recorded (`remove_list_from_netbox`). Deleting a network
  never deletes NetBox objects (`tests/test_list_delete_never_touches_netbox.py`).
- **Every write** needs the master switch (`netbox_guard.writes_allowed`) and a declared authority
  (`netbox_guard.for_list(..., authority=...)`), one writer per network at a time
  (`netbox_guard.list_writer`).

## 7. Monitoring: a site label, no NetBox plugin

**Prometheus.** `prometheus_targets.generate` adds `site` to each group's labels beside `device`
and `role`. Its value comes from the one owner (section 4): a NetBox network's `_site`, a local
network's manifest entry, or the network's name when neither names one. An empty site is never
invented. Every device has one by the default rule, so the label is always present.
`_differences` already compares every label a group carries, so the targets check reports a
running Prometheus whose `site` label differs from the inventory's, with no new comparison code.
A label added to a running target starts a new series for that target. Queries that select by
`device` match both the old and the new series, and history before the change carries no site.
The series count is measurement M6.

**Grafana.** A `site` variable (`label_values(up, site)`) on the dashboards Mercury builds
(`deploy/grafana/build_nmas_device.py`), and on the fleet role's dashboard, which is the
operator's to change. Panels filter with `site=~"$site"`. No NetBox data source is needed for
this (FLOWS_DESIGN.md adopts one for flow enrichment, a different job).

**Alert rules.** Rules written over these series carry `site` in their labels, so notification
policies route and group by site. Needs attention places an alert row in a site **by the
inventory's site for its device** (the same rule `_with_networks` applies to networks), never by
trusting an alert's label, which a hand-written rule may omit.

**Loki.** Streams carry no site. Alloy sets `device` from the line itself
(`scripts/host-steps/c722-device-label.sh`, read by `modules/device_logs.py`), and the line does
not know its site. Filtering by site is done in the query: a Grafana variable chained from
Prometheus (`label_values(up{site=~"$site"}, device)`) feeds `{device=~"$device"}`, and Mercury's
own log reads select the site's device names. Adding a site label to streams would mean Alloy
reading a device-to-site map that Mercury generates. That is a later option, not proposed, because
the chained variable answers the question with no new host step.

## 8. Display

Each screen below is a change to a signed-off screen and needs its mockup and the operator's
sign-off first (`tests/signed_off_screens.py`), with a manual page update (`tests/test_manual.py`).

- **Devices** (`modules/device_list.py`, `templates/v2/_devices.html`): rows grouped by site, each
  group a closed `<details>` led by its rollup: the device count and the counts by intent state
  and by reachability, worst first. Each group has a **select-all for that site**, feeding the
  existing selection bar and Actions menu. The page's summary leads with the network's counts by
  site. Search and filters apply across groups and open the groups that match. This is the
  "summary, groups" that the large-fleet rule owes (`EXCUSED["/v2/devices"]`, C450); grouping by
  site is one grouping that board can choose.
- **Topology** (`modules/topology_page.py`, `templates/v2/topology.html`): a **site overview**
  (one node per site, links between sites from the physical layer's links whose ends are in
  different sites, each link's state the worst of its members) drilling into **each site's map**.
  That map is today's map restricted to the site's devices, plus the far end of each inter-site
  link drawn as an outside node. This is also the natural answer to a network larger than
  `COLLAPSE_ABOVE`. The what-if (`what_if`) and path trace work within a site's map as today.
- **Needs attention** (`modules/attention.py`, `templates/v2/_attention.html`): rows grouped by
  network, then by site within it, by the inventory's site for each row's devices. A row naming
  devices at two sites is listed once, under each site's count, with both named. A row about
  no device (an integration, the host) stays under the network or the installation.
- **No extra level for a single-site network.** When every device of a network is in one site
  (every network today), Devices, Topology and Needs attention draw exactly what they draw now:
  no site heading, no overview, no group.

**Never let a wrong thing look right.** A device with no site recorded is drawn under the
network's own site and is right by the default rule. A device whose site **could not be read**
(the NetBox inventory read failed) is drawn under "Site not read", with the read's age and
reason, never under the default site. Absent and unreadable are different states.

## 9. Read across, write within: the All-networks scope

**Why no "All devices" list.** A device that appears in two networks is two sources of truth:
two repositories, two goldens, two credential resolutions, two holds (`modules/nsot/device_ops.py`
keys a hold by network and device name). A merged, actionable list would have to pick one, and
whichever it picked would look right while being wrong for the other. So the scope that crosses
networks is **read-only**.

**The scope.** The network picker (`templates/v2/_network_picker.html`, board N) gains one entry,
"All networks (read-only)". Choosing it is remembered per verified person, as any choice is
(`modules/network_choice.py`). Under it:

- **Needs attention, merged, with a Network column.** The rows are already installation-wide, and
  each already names its networks (C493, `attention._with_networks`). The scope adds a Network
  column (and Site, section 8), groups by network, and keeps each row's action in its own
  network (`list=` on the action, as today).
- **Devices across networks.** Each network's summary row (device count, counts by intent state
  and reachability, its reading's age), expanding to its sites and then its devices, each linking
  to the device page **in its own network** (`list=`). There are no checkboxes, no selection bar
  and no Actions. The cost is bounded: `device_list.listing` makes a fixed number of git reads per
  network, so an all-networks read makes that number times the number of networks. Above the
  bound in measurement M7 it becomes a stored reader value, never per request (the enterprise-scale
  rule).
- **Show commands across networks.** One run per network through the reads engine
  (`modules/nsot/reads.py`, `run(list_name, hosts, commands, actor, ...)`), sharing one batch id
  for the view. Each device is read with **its own network's credential** (its network's
  inventory rows, `load_saved_devices` of that network's `ListRef`), held in its own network
  (`device_ops.hold(list_name, ...)`), and recorded in its own network's read records, so each
  network's History shows its own reads. The scope allows **pure reads only**. The Tier 1
  commands that are not reads (`send log`, which writes a log line, and `term` settings:
  `modules/reads_page.py`, `what_it_does`) are refused in the scope, naming the command and the
  scope.
- **A fleet overview.** One row per network: devices, sites, the Needs attention count by level,
  the newest and oldest readings' ages, and whether its repository is pushed. Each row opens that
  network.

**Every write stays inside one network.** Under the All-networks scope no write control is drawn,
and the scope's name is a value no write route accepts. Every mutating route resolves exactly one
network (`modules/route_gates.py`; `routes/list_param.py`, `named_list`), and a POST naming the
All-networks scope is refused, naming the route and the scope, before any input is read.

## 10. Where the satellite case applies to one instance

The satellite case (item 7 of the operator's request) is mostly the kit fleet's, so it belongs in
[EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md): **device-side rollback** (configure replace with a
timer, or configure confirm, because a controller-side rollback cannot reach a site whose link
dropped) and **PAN-OS as a platform** are designed there. Three parts apply equally to one
instance whose sites sit behind slow or expensive links, and are kept here, each with its
measurement.

### 10.1 Time limits from each site's measured RTT

Today the bounds are global. `modules/connection.py`, `CONNECT_TIMEOUT_S = 35` (2.5 times the
slowest connect measured), whose comment records "per platform, and per network once P.8 exists"
as the follow-up. `nsot_config_read_timeout` is 120 s, one setting. The reachability probe
(`readers/reachability.probe`) and `connection.is_device_online` wait 2 s for ICMP and for TCP
port 22. At 500 to 800 ms RTT a 2 s probe is at most 2.5 RTTs, and an SSH connect takes several
round trips. A healthy device behind such a link would be drawn "Not answering".

**Design:** a site carries its **measured** RTT and connect time (a stored reader value: the
median and the 95th percentile over a window, with its age), and each bound for a device is
`max(the global bound, 2.5 × the site's measured value)`, written beside the measurement it came
from. A site with no measurement uses the global bound and says so. A bound never falls below
today's: a fast site behaves exactly as now. Measurement M8.

### 10.2 One "site unreachable" row, not one row per device

When the device through which Mercury reaches a site is down, every device behind it stops
answering, and Needs attention today draws one reachability row per device. **Design:** a site
with an **uplink** (the device, or devices, by which Mercury's subnets reach the site, computed
by `blast_radius`'s reasoning over committed intent: the devices whose loss cuts the site off)
gets one "Site <name> unreachable: <uplink> is not answering" row. Each device row behind it
attaches to that row (`attention._attach`, `attach_to`), as `_fold_one_cause` already folds two
rows about one cause. The row names what to do (check the uplink and its link) and clears when
the uplink answers. A device that still fails once the uplink answers stands alone again. The
analysis says what it cannot see, as `blast_radius.CAVEAT` does. If the uplink is not known (no
committed intent for it), there is no folding, and the row says why.

### 10.3 Polling and log volume per site

Prometheus scrape intervals are per job (docs/PROMETHEUS_TARGETS.md, "Scrape intervals"), and
`prometheus_targets` writes one file per platform dialect. A site on an expensive link needs a
slower interval and fewer modules for its devices. **Design:** a site declares a polling class
(for example `normal`, `constrained`), and `generate` writes the constrained site's devices into
their own target files, scraped by jobs with longer intervals. Alternatively, if the installed
Prometheus honours a per-target `__scrape_interval__` from `file_sd`, one label does it
(measurement M5). Syslog volume per site is bounded on the device (logging level and rate limit)
through the monitoring profile, as a deploy, never by dropping lines on Mercury's host. Bytes
per device per scrape and per syslog line, measurement M9, decide the classes.

## 11. Decisions for the operator (recommendations given; nothing decided yet)

1. **Region (recommended) or Tenant** as a network's NetBox container (section 3).
2. **The local network's site record**: the manifest entry (recommended), section 4.
3. **A VRF per repeating site (recommended) or site-scoped prefixes** (section 5), after M2 and M4.
4. **Management addresses unique per instance** (recommended, section 5): repeated addressing
   off the management path only.
5. **Loki by a chained variable (recommended)**, not a site label on streams (section 7).
6. **A `network` label on targets as well as `site`:** not proposed here. It would separate two
   networks' devices of one name in Prometheus, which the All-networks scope does not need
   because it reads each network through its own inventory. Recorded as a question.

## What it touches

- `modules/netbox_client.py`: `_sync_list_to_netbox_impl` (one site per distinct device site),
  `_ensure_site` (called per site; its rule unchanged), `_existing_device` (name fallback scoped
  to the region; manifest `nb:` id first), `_upsert_device` (the device's own site id on create),
  `_ensure_vrf` (per-site VRF names), `_ensure_prefix` (the scope field, after M2).
- `modules/network_source.py` (`FILTERS` gains `region`, `tenant`) and
  `modules/inventory/netbox_source.py` (`fetch_netbox_devices`' keys).
- `modules/nsot/manifest.py` (a `site` field on an entry, written only by a confirmed operation),
  and a new operation to move a local network's device between sites (preview, confirm, commit,
  record), declared in `modules/route_gates.py`, `modules/invalidation.py` and
  `modules/operation_stages.py`.
- `modules/prometheus_targets.py` (`generate`: the `site` label; per-site polling files after M5).
- `deploy/grafana/build_nmas_device.py` (the `site` variable).
- `modules/device_list.py`, `templates/v2/_devices.html`, `templates/v2/devices.html`.
- `modules/topology_page.py`, `templates/v2/topology.html`, `templates/v2/_topology_map.html`.
- `modules/attention.py` (grouping by site; the site-unreachable row through `_attach`),
  `templates/v2/_attention.html`.
- `modules/nsot/blast_radius.py` and `modules/readers/topology_graph.py` (a subnet held at two
  sites answers `unknown`).
- `modules/connection.py`, `modules/readers/reachability.py`, `modules/config_read.py` (per-site
  bounds, section 10.1).
- `modules/network_choice.py`, `routes/network_v2.py`, `templates/v2/_network_picker.html`,
  `routes/reads_v2.py`, `modules/reads_page.py` (the All-networks scope), and the manual pages in
  `docs/manual/` for every changed screen.

## Tests it needs

- **No migration:** a network whose devices name no site imports into exactly today's region,
  site and VRF (same names, slugs, RD), and its Devices, Topology and Needs attention pages
  render byte-for-byte as before (no site level).
- **Site per device:** two devices in two sites of one network produce two sites under the
  network's region; a third site Mercury did not create is adopted by slug and never re-parented
  (extends the `_ensure_site` cases); removal deletes only the tagged-and-recorded sites
  (`tests/test_list_delete_never_touches_netbox.py`'s shape).
- **The duplicate closed:** a device a person moved to another site of the region, with a shared
  serial, is found and updated, not created again; its site is not rewritten.
- **One owner:** a NetBox network's site comes from `_site` and is never written on update; a
  local network's comes from the committed manifest; the census refuses a switch over a site
  mismatch, naming the device and both sites.
- **Repeated addressing:** a second device with a management address already held in another
  network is refused at onboarding, naming both; `blast_radius.radius` over intent with one
  subnet at two sites answers `unknown`, naming the subnet (a planted case the test shows the
  check finds, and the check shown able to fail).
- **Targets:** `generate` labels every group with `site` (the default rule included); `check`
  reports a running target whose `site` differs (extend `tests/test_prometheus_targets.py`).
- **Large fleets:** at the 900-device fixture split into 12 sites, Devices draws the summary and
  closed groups (`tests/test_large_fleets.py`'s `EXCUSED` shrinks by `/v2/devices` when the board
  lands).
- **Read across, write within:** every mutating route in `modules/route_gates.py`, posted with the
  All-networks scope as its network, is refused before input (a sweep over the declared routes,
  with a floor on their count); the All-networks pages draw no checkbox or write control; a Show
  commands run across two networks writes one record in each, each read with its own network's
  credential, and refuses `send log`.
- **Site unreachable:** with the uplink not answering, Needs attention draws one site row with
  the devices behind it attached; when the uplink answers, the folding stops.
- **Per-site bounds:** a site with no measurement uses the global bound; a site's bound is never
  below the global one.
- Fixtures from real captures with minimal edits: a NetBox device record with a site and region,
  and a Prometheus `file_sd` group, both captured.

## What it must not break

- **Default and every network today:** one site, the same NetBox objects, the same pages. The
  site level appears only when a second site does.
- **NetBox ownership:** tagged AND recorded to delete, tagged OR recorded to re-parent, an
  update's before recorded, the master switch and the declared authority, one writer per network.
- **A person's placement in NetBox:** site stays off the update allowlist, so no import moves a
  device between sites.
- **Credentials:** resolution order unchanged (override, designated list, role, site, default).
  Template secrets stay network-scoped (`credentials.template_secret_key(list_name, ...)`).
- **The targets check:** `prometheus_targets.check` stays true for a network with one site. Adding
  the label is one regeneration, said in the targets row, with no Prometheus reload (`file_sd`).
- **Every write inside one network:** holds (`device_ops`), records, repositories and
  invalidation stay per network. The All-networks scope adds no write path.
- **Reach analyses never become optimistic:** an unqualified repeated subnet is `unknown`, never
  joined.
- **The wrong thing that looks right:** a device whose site could not be read is never drawn
  under the default site.

## Measurements still owed

None is taken now. Each is read-only unless it says otherwise, prints counts and names, never
values, and avoids the backup window (08:30 to 09:10 UTC) and s3.

| # | What | Method | Where |
|---|---|---|---|
| M1 | Whether any device of a network sits outside its network-named site today, and whether its serial is shared (the duplicate in section 2) | NetBox API reads: each network's region and site, then devices by `region_id`, compared by name with each network's inventory; serials compared by count only | the NMAS host against the lab NetBox, through `scripts/nmas-host nmas --` |
| M2 | Whether `_ensure_prefix`'s `site` field lands on NetBox 4.6.9 (4.2 replaced it by `scope_type`/`scope_id`) | read the scope of the prefixes Mercury created (`netbox_guard.get_created(..., "ipam/prefixes")`) | the NMAS host, the lab NetBox, read-only |
| M3 | Whether the device filters `region_id` and `region` include child regions, and `tenant` filters as expected | create a parent and child region with one site each in a disposable NetBox 4.6.9, then filter | a throwaway NetBox container on the laptop, never the lab's |
| M4 | Whether one prefix at two sites needs separate VRFs under the installed NetBox's uniqueness settings (`ENFORCE_GLOBAL_UNIQUE`, a VRF's `enforce_unique`) | create the same prefix at two sites, once in one VRF and once in two | the same disposable NetBox |
| M5 | Whether a `file_sd` group's `__scrape_interval__` label sets a per-target interval on the installed Prometheus | read the version (`api/v1/status/buildinfo`); test the label in a disposable Prometheus of that version | the lab Prometheus (read-only) and the laptop |
| M6 | The active series count, and what a `site` label adds while old series age out | `prometheus_tsdb_head_series` before and after, from the lab Prometheus | the NMAS host, read-only queries |
| M7 | `device_list.listing`'s time per network at 900 devices, and so how many networks an all-networks read may cover per request before it must be a stored reader value | time `listing` against `tests/test_scale.py`'s fixture, repeated, median and worst | the laptop, the suite's fixtures |
| M8 | Connect time and RTT behind a slow link, to set per-site bounds | add delay (`tc netem`, 600 ms) on one lab link, then record connect times and probe answers from Mercury's host over an hour | a lab run on s1 (IOS) and r2 (IOS-XE), outside the backup window, under the Phase 7 mode or the operator |
| M9 | Bytes per device per scrape (per job) and per syslog line, the input to polling classes | the uplink's `ifHCInOctets` and `ifHCOutOctets` toward one device over ten minutes with each job on and off, and Loki's ingested bytes for its stream | the lab Prometheus and Loki, read-only queries |

## Dependencies on the other four notes

- **FLOWS_DESIGN.md depends on this note.** Flow records are grouped and enriched by site, using
  this note's model (a network is a region, site per device) and its `site` label on the
  Prometheus aggregates. This note depends on nothing in it.
- **IPAM_IMPORT_DESIGN.md depends on this note** for its site and VRF mapping: which NetBox
  container a network is, that a site is per device, and that a prefix may repeat only across
  per-site VRFs or sites (section 5). Its validation's "overlapping prefixes allowed only across
  VRFs or sites" is this rule. This note depends on nothing in it.
- **EDGE_ARCHITECTURE.md reuses this note.** A kit is a network on its own instance, normally one
  site, so no site level is drawn. Headquarters' own network uses sites as designed here. Per-site
  time limits and the site-unreachable row (section 10) carry over to a kit's own instance.
  Device-side rollback and PAN-OS are designed there, not here. The headquarters manager's view
  across kits is EDGE's (across instances). This note's All-networks scope covers several
  networks on one instance only, and its rule, read across and write within, is the same idea.
- **BRINGUP_FROM_DOCUMENTS.md** has no direct dependency on this note. The values it extracts
  land in the kit's network, whose default site is the network's own name. A kit's node number is
  part of its identity (EDGE), not a site.
- [OFFLINE_OPERATION.md](OFFLINE_OPERATION.md), the sixth note, needs nothing from this one.
