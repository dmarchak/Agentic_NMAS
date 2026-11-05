# NetBox planning, discovery and onboarding (a design; nothing is built)

**Design only, written 2026-11-05 from the operator's design of the same day.** It is built after
both labs (Lab 10, due 2026-11-23, and Lab 9, the final SDN lab, due 2026-11-30;
docs/PHASE8_PLAN.md section 0.3). Nothing below is built. Every statement about Mercury was read in
the code at `1e9b4bef` and names its file and line. Every statement about another product names
the page it was read from and the date (2026-11-05). What could not be checked is marked **(to
confirm)** and listed in section 16.

**Charter bucket: CORE.** The charter's "New devices: Mercury is a front door to NetBox, never a
second inventory" (docs/MERCURY_CHARTER.md) names the two entry points this design builds:
- "Pick a Planned device from NetBox";
- "Create one in Mercury", written into NetBox first as Planned.

It also carries docs/NSOT_STAGE10_PLAN.md 7.3's required **Bulk onboarding** item, designed in
docs/NSOT_STAGE7_PLAN.md section 17, and docs/NSOT_OWNERSHIP.md's Phase 1 (identity) and Phase 3
(discovery as proposal).

## The principle (the operator, 2026-11-05)

- **NetBox is the source of truth for devices.** No path creates a Mercury device that is not in
  NetBox.
- **Planning is separate from onboarding.** Planning designs what should exist; onboarding brings
  a planned device to life.
- **Discovery reduces hand entry,** but its facts are proposals, never silent overwrites.
- **Credentials stay on Mercury's Credentials page,** never in NetBox (docs/MERCURY_CHARTER.md,
  "Credentials: the one accepted exception").

The design has four parts:
1. **Add device** (onboarding) from the Planned records NetBox holds (section 3).
2. **Plan devices**, which writes Planned records only (section 4).
3. **Discover a device**, the low-typing path that ends in a Planned record (section 5).
4. **The management port**, one rule that every part, and the rest of Mercury, reads (section 6).

## 1. What exists today

### 1.1 "Pick a Planned device": a name typed, then matched

There is no list of Planned records to pick from. Add device's form asks for a **Name**
(`templates/v2/_onboard_add.html` L57-L58: "a name NetBox holds must be Planned there"), and the
plan reads NetBox's record of that name.

**The read.** `modules/nsot/device_environment.py` `read` (L101) finds devices by name, raises on
more than one, and reads:
- the record;
- its `mgmt_only` interfaces, which become the environment's reserved interfaces;
- its role, and the role's `mercury_kind`;
- the config context's `environment_owned_lines`.

`_record` (L148) keeps the record's id, status, site, role, kind, platform, tags and URL.

**How onboarding judges it** (`modules/nsot/onboard.py`):
- `planned_record` (L365) is true when the status is `planned` (C676).
- `planned_netbox_id` (L370) keeps the record's id in the plan and its fingerprint, and in the
  manifest entry Create writes (C1598).
- `netbox_problems` (L397-L425) refuses any other status, naming it. It also refuses a Planned
  record whose platform, or whose role's kind, disagrees with the form. Both values are named, and
  NetBox owns both.
- `netbox_note` (L377-L395) tells the review screen that nothing is written in phase 1.

**What is typed although NetBox could answer it:**
- the management address, mask, MAC, management interface and gateway (`_onboard_add.html`
  L76-L85);
- the platform management port (L91-L92);
- the domain (L94).

Only the out-of-band (console) path derives the address from the Planned record:
`modules/nsot/oob_onboard.py` `_planned` (L200) and `_planned_address` (L282) take the record's
primary IPv4 address, else its one assigned address. An IPv6 address is refused there by name
(C1245).

**Success sets Active.** `activate_planned` (`modules/nsot/onboard.py` L1796, C1421) moves the
Planned record to Active through the write gate and reads it back. Abandon keeps a Planned record
that Create read and never deletes it (`_keep_planned_record`, L2339).

### 1.2 "Create in Mercury": NetBox is written last, not first

The charter's entry point 2 says the device is "written INTO NETBOX FIRST as Planned, as a
confirmed step". **The code does the opposite.**
- **Create writes nothing in NetBox.** `netbox_note` says so (L381-L383): "the NetBox record is
  created in phase 2, from the device's first capture".
- **The record is made at Verify.** `create_netbox_record` (L1651) runs the importer on the
  device's first golden. With no capture yet, it defers and creates nothing (L1680-L1693).

So a device named in Add device that NetBox does not hold is a Mercury device before it is a
NetBox one. This contradicts the principle (proposed row R4, section 15).

**The write gate is a precondition.** `unmet_preconditions` (L1057) refuses a run that would
create NetBox objects while writes are off, and never turns them on by itself. A fresh install
cannot turn them on through Mercury: C2548, which is open and B.

### 1.3 The import into NetBox: goldens, not a live scan

**The brief's premise, and C2553's, do not match the code.** Both say the import scans each device
by SSH (`show version`, `show inventory`) with `_parse_device_facts`. What the code does:
- **`_parse_device_facts` has no caller.** `modules/netbox_client.py` L1893 is its definition
  and its only occurrence in the repository.
- **The SSH scanner was removed in Stage 3.3,** as the comment at L1946-L1957 says ("Nothing
  called it").
- **The module docstring still describes it** (L9-L11: "Every device in a list is scanned via SSH
  (show version / show inventory)"). This is a document asserting what the code lacks (proposed
  row R2).

**What the import really reads:** `_scan_device_from_golden` (L3401), from the device's committed
golden:
- facts by `_parse_facts_from_config` (L3143), which sets manufacturer `"Cisco"`, model
  `"Unknown"` and serial `""` outright, and takes the version and the IOS / IOS-XE / NX-OS family
  from the config's text;
- interfaces, VRFs, VLANs, static routes, protocol tags and routing context from the config;
- a DHCP-addressed interface given its leased address from the manifest (C1442).

**The one live part.** `_fetch_neighbors_live` (L1959) sends `show cdp neighbors detail` and
`show lldp neighbors detail` to devices the status cache reports online (L3795-L3815), and parses
them with Cisco patterns. The LLDP cable pass also reads the Topology reader's stored LLDP
(`stored_lldp_links`, C1344).

**What a sync creates and updates** (`_upsert_device`, L2306; its preview is `netbox_ops.dry_run`,
`modules/netbox_ops.py` L323):
- the region, site and VRF of the list;
- manufacturer, device type, role and platform, each got or created (`_ensure_manufacturer` L572
  defaults the name to `"Cisco"`; `_ensure_device_type` L582 creates a type with `u_height` 1 and
  no interface templates);
- the device;
- interfaces with MAC, MTU, speed and state (`_ensure_interface` L1108, writing `mac_address`
  L1136-L1164);
- prefixes, IP addresses, VLANs and VRFs;
- `primary_ip4` and `primary_ip6` (L2874-L2975);
- the sanitised config context;
- cables from LLDP.

**Which record a sync updates:**
- the Planned record by its id when onboarding names one (`_record_by_id` L2293);
- else the id the manifest recorded (`_recorded_record`);
- else by serial only when it is unique, then by name and site (`_existing_device` L2245).

**So the conclusion of C2553 stands, on different evidence.** The import is Cisco-only because
its facts come from Cisco configuration text, and its live neighbour read sends Cisco commands. A
non-Cisco device has no golden and cannot be brought in by it.

### 1.4 The NetBox write gate and its confirm

**Three chokepoints.** `_nb_post`, `_nb_patch` and `_nb_delete` are the only write paths, and each
asks the master switch (`modules/netbox_guard.py` docstring item 1; `writes_allowed` L123,
`assert_writes_allowed` L129).

**A dry run runs the real code.** Inside `netbox_guard.dry_run` (L264) the same helpers record
each write and return a synthetic object, so the preview is exactly what the write would do.

**Provenance.**
- Every created object is tagged `nmas-managed` and recorded (`record_created`, L829).
- Every update records its before (`record_modified`, L611).
- Removal deletes only what is both tagged and recorded.

**One writer per network,** across processes (`list_writer`, L1070). A second writer is refused,
naming the first.

**The confirm.**
1. `netbox_ops.authorization_for` (`modules/netbox_ops.py` L88) issues a one-shot token bound to
   the plan's hash (`modules/netbox_authz.py`, a 300 s life).
2. `authorize` (L99) consumes the token, recomputes the plan and refuses if it moved.
3. Only then may the confirm turn the master switch on with `permit_writes` (C330).

Operations today: `import`, `import_all`, `remove`, `forget`, `free` (L28). There is no
operation that writes a Planned record.

### 1.5 Discovery and its captures

`modules/discovery.py` (docs/LAB9_DISCOVERY.md) is **read-only access to a device Mercury has no
driver for.** It is not discovery of unknown devices.
- **A positive allowlist per Netmiko driver** (`DRIVERS`, L87): Arista EOS, ProCurve /
  ArubaOS-Switch, AOS-CX through netmiko's `aruba_os` (C2529), Comware and Open vSwitch.
- **Commands.** Each driver's capture list is whole commands (L56-L83). Any other command is
  refused, and so is every configuration, save and commit call.
- **Masking.** Every answer is masked by `redact_text`, then by `mask_lines` (C2528: EOS, AOS-CX
  and ProCurve credential lines pass `redact_text`).
- **The captures** are the reads engine's own records (`modules/nsot/reads.py`), named
  `<device>/<command>/<run id>` (docs/LAB9_DISCOVERY.md section 5).

**What it does not do** (docs/LAB9_DISCOVERY.md section 6, and C2527): it creates no NetBox
record, so the lab's switches enter NetBox through NetBox's own UI or its bulk import.

**Two other things share the name:**
- **Board L's "Discovered" page** (`modules/discovery_page.py`) lists devices asking on the ZTP
  segment, from the DHCP reader.
- **Platform facts** (`modules/readers/platform_facts.py`) keeps every SNMP-polled device's
  `sysDescr` and `sysObjectID` from one Prometheus query.

Neither reads a device that Mercury does not already poll.

### 1.6 The management interface today

There are four definitions, in four places:
- **The device's environment** (`device_environment.read`): its `mgmt_only` interfaces, where the
  manager's address never goes.
- **OpenFlow** (`modules/sdn/openflow_values.py` `management_reason`, L161): an interface NetBox
  marks `mgmt_only`, or one holding the primary IP (IPv4 or IPv6), or one holding `oob_ip`. It is
  left out of `ports` even when tagged `openflow`. A device whose only tagged interfaces are
  management ones is refused, and so is an OpenFlow VLAN equal to the management VLAN
  (L15-L21). **Built, at `1e9b4bef`.**
- **Mode B and heal** (`modules/nsot/removal.py` `_management_interfaces`, L492): read from the
  running configuration. It is the interface holding the address the tool connects to, or one
  addressed by DHCP. A removal there is refused as "the management path" (L539-L541), and heal
  classifies it Tier 4 (`modules/heal/kinds.py` `_mgmt`, L225).
- **The port bounce's guard 13c** (docs/HEAL_TO_INTENT.md 19.4, N17 in 19.10) is designed and not
  built; H20 builds it. The only code of it is the revert probe's reading,
  `scripts/nmas-revert-probe` `path_refusal` (L385), with three checks:
  1. the interface carries the management address, read by the device's own brief;
  2. the device's `show ip cef <Mercury's address>` names it as the egress;
  3. it is the device's only path.

**The NetBox-sourced inventory** (`modules/inventory/netbox_source.py` `adapt_devices`, L130-L134)
reads `primary_ip4` only. A device with an `oob_ip` and no primary IPv4 is skipped ("no primary
IPv4 address set in NetBox"), and so is an IPv6-only device (C1245).

### 1.7 What each lacks against the design

| Today | Lacks |
|---|---|
| Add device (1.1) | a list of Planned records to choose from, with search and filters by site and role; multi-select; prefill of the management address, interface, MAC and platform from NetBox; a "not ready, missing X" state before the form |
| Create in Mercury (1.2) | the Planned record written first, as a confirmed step; a duplicate check on name, address and serial before it |
| The import (1.3) | any non-Cisco fact; the model and serial at all (always `Unknown` and empty); a device type from a library with its interface templates; facts as proposals rather than writes |
| The write gate (1.4) | an operation that writes Planned records; a way to turn writes on in a fresh install (C2548) |
| Discovery (1.5) | platform detection; a fact read set per vendor with parsers; a subnet sweep; any NetBox write; drift on re-discovery |
| The management interface (1.6) | one owner of "which interface is management"; the inventory reading `oob_ip` and IPv6; the bounce refusing a NetBox-declared management interface before it reads the device |

## 2. The industry need, per feature

The rule is CLAUDE.md, "Every feature states its industry need". Every page below was read
2026-11-05.

### 2.1 The problem engineers have

- **Typing every device twice.** Engineers type each device into a DCIM or IPAM tool, then
  again into the management tool. The two copies drift.
- **No migration path.** A fleet's first import is a spreadsheet or a subnet, not one device at
  a time.
- **Unreviewed discovery.** Discovered facts written straight into the source of truth make it
  a copy of the network, mistakes included. Hand-kept facts are never checked against the
  devices.

### 2.2 How established tools do it

**NetBox's own bulk import:**
- It takes CSV, JSON or YAML, and detects the format
  (https://raw.githubusercontent.com/netbox-community/netbox/main/netbox/utilities/forms/bulk_import.py).
- It updates instead of creating when an `id` column is present, and "only the columns present in
  the data are applied" (https://netboxlabs.com/docs/netbox/getting-started/populating-data/).
- Device types take YAML, not CSV, so their components import with them (same page).
- The import runs in one database transaction: "any violation rolls back the entire import"
  (https://raw.githubusercontent.com/netbox-community/netbox/main/netbox/netbox/views/generic/bulk_views.py).
- A device "will automatically inherit the components (such as interfaces) of its device type at
  the time of creation"
  (https://raw.githubusercontent.com/netbox-community/netbox/main/docs/models/dcim/devicetype.md).
  `InterfaceTemplate.instantiate()` copies `mgmt_only`
  (https://raw.githubusercontent.com/netbox-community/netbox/main/netbox/dcim/models/device_component_templates.py).
- What it lacks: a column-mapping step, cross-row checks (an address inside the site's
  management prefix, two rows given one address) and a plain-language preview. It matches on
  `id`, not on name.

**Nautobot's Device Onboarding app**
(https://docs.nautobot.com/projects/device-onboarding/en/latest/user/app_use_cases/,
.../app_getting_started/, .../app_detailed_design/):
- **"Sync Devices From Network"** takes a location and IP addresses (or a CSV) and creates the
  device "with its management interface and its primary IP assigned".
- Credentials come from a secrets group.
- The platform is detected by Netmiko's SSH autodetect unless one is given.
- A device that already exists matches on hostname AND serial. A changed serial is skipped with a
  warning unless "Update Devices With Changed Serial" is set.
- **"Sync Network Data From Network"** adds interfaces, addresses, and optionally VLANs and VRFs.
- What it lacks: its sync writes directly; there is no preview a person confirms by hash.

**Nautobot's Device Lifecycle Management app**
(https://docs.nautobot.com/projects/device-lifecycle/en/latest/user/app_overview/) tracks:
- hardware end-of-life notices;
- validated software;
- contracts;
- CVEs mapped to devices.

It is outside this design. It is named because the serial, model and version that discovery
proposes are its inputs.

**IP Fabric:**
- It discovers from seeds and from neighbours: routing next hops, ARP, CDP, LLDP and IPv6
  neighbour discovery (https://docs.ipfabric.io/7.5/overview/How_Discovery_Works/CLI_discovery/,
  https://docs.ipfabric.io/7.5/overview/How_Discovery_Works/troubleshooting_discovery/).
- It reads by show commands, and "Read-only (Privilege 1) credentials are sufficient", with a
  credential limited by subnet
  (https://docs.ipfabric.io/main/IP_Fabric_Settings/Discovery_and_Snapshots/Discovery_Settings/device_credentials/).
- It is a snapshot tool. It does not write a source of truth.

**Forward Enterprise:**
- A device is a hostname or address. The collector "will attempt to automatically determine the
  correct device type and credentials" (https://docs.fwd.app/25.9/api-doc/).
- Neighbours missing from a snapshot are listed for adding (same page).
- CSV import and subnet scans: (to confirm; the community page refused the fetch).

**SolarWinds NPM's Network Sonar:**
- It scans IP ranges, subnets, single addresses or a seed router's routing table, with SNMP
  credentials, ICMP-only devices as an option, and a results wizard where a person picks what to
  import
  (https://documentation.solarwinds.com/en/success_center/npm/content/npm-orion-network-sonar-wizard-sw50.htm).
- Discovery is scheduled, and "a maximum of a /23" per subnet scan is recommended
  (https://documentation.solarwinds.com/en/success_center/orionplatform/content/core-network-discovery-using-the-network-sonar-wizard-sw1574.htm).

### 2.3 How Mercury meets it, and where it improves

- **One store, one direction.** NetBox holds the design. Mercury plans into it, onboards from it,
  and never keeps a second inventory (the charter).
- **Discovery proposes, a person decides.** No other tool above previews its source-of-truth
  writes field by field and binds a person's confirm to a hash of exactly what is written
  (CLAUDE.md, "What is confirmed is what is sent").
- **Re-discovery is drift, not a silent update.** A changed serial on the same name is a Needs
  attention row a person resolves, not a skipped device or an overwrite.
- **Scale.** Lists summarise, group, filter and search. Reads run concurrently. Every per-device
  question is a job (sections 8 and 12).

## 3. Add device (onboarding), from NetBox

### 3.1 The main path: NetBox's Planned devices, not yet in Mercury

Add device opens on one list:
- **What is listed:** NetBox's devices with status Planned in the network's NetBox scope (its
  filter: site, tenant or tag; docs/NSOT_OWNERSHIP.md part 2, decided item 4).
- **Not yet in Mercury** means no manifest entry, onboarding pending or done, holds the record's
  id or name.
- **The summary leads,** by the large-fleets rule: "38 Planned · 31 ready · 7 not ready ·
  2 being onboarded".
- **Groups,** each collapsed but the first: Ready, Not ready, Being onboarded.
- **Filters** by site and role, and a search by name, address or serial. The page says when it
  shows a subset.
- **Multi-select** over the Ready group, with "select all N shown".

**Where it is read from.** A reader job keeps the list: one NetBox query per network on an
interval (`reader_job`). It is announced when it changes, and later prompted by a NetBox Event
Rule on a device created as Planned (docs/NSOT_OWNERSHIP.md part 4, decided item 3). Never a NetBox
call per page view (CLAUDE.md, "Enterprise scale"). When NetBox is unreadable, the last good list
stays, dated, as a row of its own.

### 3.2 Everything prefilled from NetBox

**Read with the record** (one read per device, in the reader):

| Field | From NetBox |
|---|---|
| Name | the record's name |
| Site, role | the record's; the role's `mercury_kind` gives Mercury's kind (`modules/inventory/role_kind.py`) |
| Platform, and so the driver and dialect | the record's platform slug, through the one platform map (Settings › Installation › Platforms and roles; `inventory/netbox_source.map_platform`) |
| Management interface, address and its prefix length | section 6's resolver: the one management address and the interface it is on |
| Management MAC | that interface's MAC, needed by the DHCP and ZTP methods (a reservation) |
| Gateway | the management prefix's gateway: the address NetBox marks as its gateway (to decide; section 14, decision 7) |
| Interfaces | the record's interfaces, from its device type's templates |
| Domain | the network's setting, as today |

The person then picks the devices and one method: Static, DHCP, ZTP, Out-of-band (console), or
Adopt for a device already running with a login.

**The methods' own fields** are asked only when NetBox cannot answer them:
- ZTP's route option and boot file stay derived as today.
- The console's uplink is derived from NetBox's cable (`oob_onboard.derive`).

The review is today's single-device review (`onboard.build_plan`, its fingerprint and confirm),
one per device or one batch review (3.4).

### 3.3 Not ready: what is missing, and a link to fix it

A Planned record that onboarding cannot use is listed under **Not ready**, naming each missing
fact. It cannot be selected.

| Missing | The words |
|---|---|
| no management address | "edge1 has no management address: plan one on its management interface (Plan devices › edge1)" |
| two or more candidate addresses | "edge1 has 2 addresses that could be its management address (192.0.2.11 on Management1, 192.0.2.12 on Vlan99): exactly one management address per device" |
| no platform | "edge1 names no platform: the driver depends on it" |
| a platform with no driver row | "platform arista-eos has no row in Platforms and roles" (a link to that page) |
| a role with no `mercury_kind` | the role named, and where to set its kind |
| a MAC, for DHCP or ZTP only | "the DHCP method needs Management1's MAC; Static and Out-of-band do not" (judged per method, so a device is never refused for a method nobody chose) |
| no credential profile covering it | the role or site resolved, and a link to Credentials › Profiles (the secret is never shown) |
| NetBox unreadable for this record | the read's error: a different state from "missing" (CLAUDE.md, "absent and unreadable are different states") |

**Each link** opens the device in Plan devices (section 4), so the person never leaves Mercury
for NetBox (C1445). NetBox's own page is offered beside it for audit.

### 3.4 Bulk onboarding

This is docs/NSOT_STAGE7_PLAN.md section 17, with NetBox as its source:
1. **Validate before anything connects.** Every check of 3.3 per device, plus duplicates across
   the selection (two records with one address).
2. **A read-only dry run per device,** in parallel (`fanout.read_each`): is it reachable, does
   its profile log in, does its platform answer as declared? The answer is a summary: ready,
   unreachable, wrong credentials, wrong platform.
3. **One confirm for the batch.** It binds a hash over every device's own plan fingerprint.
4. **A batch job.** Each device runs the single-device pipeline. The batch holds each device in
   turn, with `deploy.run_batch`'s circuit breaker. Only failures are retried.
5. **End of batch, once:**
   - seeding, one review: N clean, M need a look (section 17, item 6);
   - break-glass, one export.

## 4. Plan devices: Source of Truth › NetBox › Plan devices

A separate page under the NetBox page (`routes/netbox_v2.py`; its sidebar item is
`templates/v2/base.html` L67). It writes **Planned records only**:
- a device;
- its management interface, when that is a VLAN interface or a loopback;
- its management IP address, as primary IP or OOB IP.

It never writes a record's status past Planned, and never touches a record that is not Planned.

### 4.1 One device

**The form:**
- **Name**, unique in NetBox. A taken name is refused, naming the holder and its status.
- **Site, role, device type, platform:** choices read from NetBox. Never typed, never created
  here.
- **The Management section** (section 6.1).

**Interfaces come from the device type's interface templates, never typed.** NetBox instantiates
them when the device is created (section 2.2). The form shows the type's templates read-only,
with each one's `mgmt_only` mark, so the person sees what the device will have.
- A type with no interface templates is allowed, and said: "Generic switch has no interface
  templates: the device is created with none, and its management interface must be a VLAN
  interface or a loopback."

**The preview** is a dry run of the real write inside `netbox_guard.dry_run`, shown through the
normal NetBox confirm (1.4): each object to create, in order, and its fields. The confirm is a
new `netbox_ops` operation, `plan`. Its hash covers every object, and the master switch is
honoured as for an import. The result is read back and recorded in History.

### 4.2 Bulk: CSV or Excel, mapped, validated, previewed, confirmed

**The template.** A downloadable CSV whose columns are NetBox 4.6's own import field names, where
a field means the same thing (DeviceImportForm's `name`, `site`, `role`, `manufacturer`,
`device_type`, `platform`, `serial`, `asset_tag`, `tags`, `description`). Two things follow:
- **The management columns** are Mercury's: `mgmt_interface`, `mgmt_address` and `mgmt_vlan`
  (section 6.3).
- **There is no status column.** Every row is Planned. A row naming another status is refused,
  naming it.

So a file prepared for NetBox's own device import maps with no step at all.

**The flow:**
1. **Upload** a `.csv`, or an `.xlsx` (only `.xlsx`: a legacy `.xls` or a `.xlsm` is refused by
   format, and no macro is run).
   - Bounded in size and rows before parsing, the bounds about 2.5 times a measured large file.
   - Parsed as untrusted input (docs/IPAM_IMPORT_DESIGN.md section 4.1).
2. **Map the columns.** Each header is matched to a field by exact name, then by a short alias
   table (for example `hostname` to `name`, `model` to `device_type`).
   - The person confirms or changes each mapping.
   - A header that looks like a credential (`password`, `secret`, `community`, `key`) is
     refused: NetBox holds no secret (`tests/test_netbox_holds_no_secret.py`).
   - The confirmed mapping is saved per network for the next upload.
3. **Validate before any write,** in code, before NetBox is asked to write:
   - every site, role, device type and platform exists in NetBox;
   - the required fields are present: name, site, role, device type, and a management address or
     a reason the type's templates answer;
   - no duplicate names within the file;
   - no name held in NetBox by a record that is not Planned;
   - every address is shaped as `ipaddress.ip_interface`, in the site's management prefix (6.2),
     and not already in use in NetBox or twice in the file;
   - `mgmt_vlan` is 1 to 4094 and exists at the site;
   - `mgmt_interface` exists in the type's templates when it names a physical port.
4. **The row-by-row preview** (a dry run of the real writer):
   - each row is Create, Update, Unchanged or Refused;
   - each problem is named with its row, column, the value as read, the comparison made and both
     operands;
   - nothing is written while any row is refused, unless the person sets those rows aside, which
     is said in the confirm and in the hash.
5. **Confirm through the normal NetBox confirmation** (`plan`, 4.1).
6. **The results per row,** read back from NetBox: created (its id), updated (the fields changed,
   before and after), unchanged, or failed (NetBox's error, verbatim and masked).
7. **The upload is recorded in History:**
   - who, when, the file's name, its SHA-256 and row count, the mapping's hash;
   - the plan's hash and the results;
   - never the file itself.

**Re-uploading updates, never duplicates.** A row matches a NetBox device by name, within the
network's NetBox scope:
- a Planned record of that name is updated, with the before recorded;
- a record of another status is refused, as in validation;
- an optional `id` column, NetBox's own convention, renames: that record is matched by id and its
  name changed, said in the preview.

**Large files.** The preview leads with counts by outcome and by problem, groups and collapses,
and searches by name and address. A row's detail opens on expand (CLAUDE.md, "Built for large
fleets").

### 4.3 The IPAM-spreadsheet requirement, folded in here

The earlier requirement is in three places:
- **docs/IPAM_IMPORT_DESIGN.md** (C1006; docs/COMPLETION_INVENTORY.md K55, "IPAM import from a
  spreadsheet"): a one-way, one-time import of an organisation's IPAM workbook into a kit's
  NetBox, staged at headquarters against a signed mapping profile.
- **docs/NSOT_STAGE7_PLAN.md section 17** ("Upload a CSV or XLSX ... A column mapping, saved for
  reuse").
- **docs/EDGE_ARCHITECTURE.md** and **docs/BRINGUP_FROM_DOCUMENTS.md**, which name the
  spreadsheet as a source.

**Plan devices' bulk upload is their device half.** Plan devices takes devices with their
management addresses. The IPAM import's other objects stay that design's: prefixes, ranges, VLAN
groups, VRFs and fill-colour statuses. The two share these pieces, built once:
- **the workbook reader** (docs/IPAM_IMPORT_DESIGN.md section 4.1: openpyxl, MIT, a shipped
  licence and so the operator's decision; section 14, decision 3);
- **the mapping step:** the confirmed mapping here is that design's mapping profile, in its
  simplest form, one sheet and one header row;
- **validation by code before any write,** with each problem in two voices (its section 6);
- **the writer on Mercury's chokepoints** (its section 9.4, recommended there over Diode and over
  NetBox's own bulk import, for the same reasons: the confirm bound by hash, provenance and undo).

docs/IPAM_IMPORT_DESIGN.md gains one line naming this design as its device half.

## 5. Discover a device: the low-typing path, ending in a Planned record

### 5.1 A minimal record

The person gives four facts:
- the management address;
- the credential profile (from Credentials, never a typed secret);
- the site;
- the role.

The name may come from the device's hostname. Discovery reads the device read-only and proposes
the rest, and the proposal becomes a Planned record through Plan devices' own confirm (4.1). The
device is then onboarded or adopted from that record (section 3).

### 5.2 Platform auto-detection

**SNMP first, when the network has an SNMP credential.**
- `sysObjectID` names the vendor's enterprise number, and `sysDescr` the family.
- Mapped by a table kept as data, seeded from netmiko 4.3.0's `SNMP_MAPPER_BASE`. It holds 18
  device types: arista_eos, allied_telesis_awplus, paloalto_panos, hp_comware, hp_procurve,
  cisco_ios, cisco_xe, cisco_xr, cisco_asa, cisco_nxos, cisco_wlc, f5_tmsh, fortinet, checkpoint,
  juniper_junos, nokia_sros, dell_powerconnect, mikrotik_routeros (netmiko's
  `snmp_autodetect.py` in the lock's copy; and
  https://raw.githubusercontent.com/ktbyers/netmiko/v4.3.0/netmiko/snmp_autodetect.py).
- **SNMP needs a credential from Credentials:** a v2c community or a v3 user. Mercury holds one
  per network as a monitoring-profile secret (`credentials.profile_secret_key`), and discovery
  reads it there. Without one, detection is SSH only, said.
- **How SNMP is asked is a decision** (section 14, decision 5):
  - pysnmp left the lock with the AI family's trap receiver (`requirements.txt`, "pysnmp left");
  - netmiko's SNMPDetect imports pysnmp and does not install it;
  - the deployment already runs snmp_exporter, whose probe endpoint answers one target's
    `system` module (to confirm, on one device).

**SSH next, through Mercury's own session.** netmiko 4.3.0's `SSH_MAPPER_DICT` detects 39 device
types (the lock's `netmiko/ssh_autodetect.py`; and
https://raw.githubusercontent.com/ktbyers/netmiko/v4.3.0/netmiko/ssh_autodetect.py): alcatel_aos,
alcatel_sros, allied_telesis_awplus, apresia_aeos, arista_eos, ciena_saos, cisco_asa, cisco_ios,
cisco_xe, cisco_nxos, cisco_xr, cisco_xr_2, dell_force10, dell_os9, dell_os10, dell_powerconnect,
f5_tmsh, f5_linux, hp_comware, hp_procurve, huawei, juniper_junos, linux, ericsson_ipos,
extreme_exos, extreme_netiron, extreme_slx, extreme_tierra, ubiquiti_edgeswitch, cisco_wlc,
cisco_wlc_85, mellanox_mlnxos, yamaha, fortinet, paloalto_panos, supermicro_smis, flexvnf,
cisco_viptela, oneaccess_oneos. **`aruba_aoscx` is not among them** (C2529).

**Mercury does not run SSHDetect itself.** In the lock's netmiko 4.3.0, `SSHDetect.__init__`
calls `ConnectHandler` directly (`netmiko/ssh_autodetect.py` L358). That bypasses `open_ssh` and
its host-key policy (`modules/connection.py` L491). `_send_command` writes each command to the
channel raw (L423), outside the session's read-only guard (`connection._guard_writes`, L659). Its
commands include `cat /etc/issue`, `uname -a`, `software show` and `get system status`, which are
on no allowlist. It sleeps 1 s and reads for 6 s per command.

So Mercury builds its own probe, by CLAUDE.md's rules ("Refusing by resemblance is safe, allowing
by resemblance is not"; "No terminal steps"):
- the session is opened by `open_ssh`, keeping the first contact's host key as every session does
  (docs/LAB9_DISCOVERY.md section 2, step 4), and the proposal shows the key's fingerprint;
- the probe sends only a fixed positive list, in order, stopping at the first match:
  `show version`, then `display version`;
- netmiko's search patterns are reused as data, so the 20 of its 39 entries that use
  `show version`, and the two that use `display version` (Comware and Huawei), are detectable;
- the rest (F5's `show sys version`, Fortinet's `get system status`, Palo Alto's
  `show system info`, Linux's `uname -a`, and so on) are **not detected**, said by name: "not
  detected: choose its platform";
- each probe command is bounded at about 2.5 times its measured answer time (unmeasured; the
  first build measures it on s1 and r2, never s3);
- the platform found must have a row in Platforms and roles. Without one, the proposal says so and
  links there.

### 5.3 The facts, read-only, through the masked show-command path

**How the facts are read.** Each family's fact commands become a capture list in
`discovery.DRIVERS` (a positive allowlist per driver, each command whole), or the existing
read-only allowlist for the Cisco dialects. They run through the reads engine, masked by
`redact_text` and then `discovery.mask_lines`, and are kept as captures (1.5). The facts read:
- hostname, vendor, model, serial, software version, hardware inventory;
- every interface: its name, type, MAC, MTU, description and addresses;
- LLDP and CDP neighbours, which propose cables.

**The parsers** are ntc-templates where they exist:
- **ntc-templates 3.5.0 is already in the lock**, through netmiko, with TextFSM 1.1.3.
  - Both are Apache-2.0 in `docs/THIRD_PARTY.json`. The upstream licence was read again in
    https://raw.githubusercontent.com/networktocode/ntc-templates/master/pyproject.toml and
    https://github.com/google/textfsm/blob/master/LICENSE.txt.
  - So no new licence is needed for them.
- **The templates were read from the lock's own index** (`ntc_templates/templates/index` in the
  CI interpreter's site-packages, 635 lines).
- **Where a template is absent,** Mercury's own parser is built from a real capture
  (CLAUDE.md, "Fixtures are real captures"). Lab 9's captures are the first.

| Family (driver) | Identity: hostname, model, serial, version | Inventory | Interfaces (name, type, MAC, MTU, description) | Addresses | Neighbours | Templates absent in 3.5.0 |
|---|---|---|---|---|---|---|
| Cisco IOS, IOS-XE (`cisco_ios`, `cisco_xe`) | `show version` | `show inventory` | `show interfaces` | `show ip interface brief`, `show ipv6 interface brief` | `show lldp neighbors detail`, `show cdp neighbors detail` | none for IOS; **`cisco_xe` has no templates of its own**: IOS-XE output is parsed with the `cisco_ios` templates, as netmiko's own fallback does (https://raw.githubusercontent.com/ktbyers/netmiko/v4.3.0/netmiko/utilities.py); `show ipv6 interface brief` (to confirm) |
| Cisco NX-OS (`cisco_nxos`) | `show version` | `show inventory` | `show interface` | `show ip interface brief` (to confirm) | `show lldp neighbors detail`, `show cdp neighbors detail` | none of the core five |
| Arista EOS (`arista_eos`) | `show version`, `show hostname` (to confirm) | `show inventory` | `show interfaces` | `show ip interface brief` | `show lldp neighbors detail` (EOS's CDP is not read) | none of the core four |
| Juniper Junos (`juniper_junos`; no discovery driver yet) | `show version` | `show chassis hardware` | `show interfaces` | from `show interfaces` | `show lldp neighbors` | none of the core four |
| HP ProCurve, ArubaOS-Switch (`hp_procurve`) | `show system` | none | `show interfaces`, `show interfaces brief` | `show ip` (to confirm) | `show lldp info remote-device` (and its detail form) | `show version`, a model source: Mercury's own parser |
| AOS-CX (`aruba_os` today; `aruba_aoscx` after C2529) | `show system` | `show module` (to confirm) | `show interface` | from `show interface` | `show lldp neighbors-info detail` | `show version`: Mercury's own parser |
| HP Comware (`hp_comware`) | `display device manuinfo` (model, serial) | `display device manuinfo` | `display interface` | from `display interface` | `display lldp neighbor-information verbose` | **`display version`**: Mercury's own parser, from a capture |
| Open vSwitch (`ovs_linux`) | `ovs-vsctl --version`, the bridge reads (`modules/sdn/ovs.py`) | none | `sudo -n ovs-vsctl show` | none read | none | all: Mercury's own shapes, as today |

**The answering interface** (section 6.4) is the interface whose address is the one Mercury
connected to. It is read from the same address reads, so it costs no extra command.

### 5.4 The model mapped to a NetBox device type, from the community devicetype-library

**The library:**
- netbox-community/devicetype-library: one YAML file per model, by manufacturer
  (`device-types/<Manufacturer>/<model>.yaml`; its `CONTRIBUTING.md` and `README.md`).
- Each interface entry carries `name`, `type` and `mgmt_only`. Licence **CC0-1.0**
  (https://github.com/netbox-community/devicetype-library, read 2026-11-05).

**The mapping:**
- The model, or part number, that discovery read is matched to the library's `model` and
  `part_number` fields, within the manufacturer.
- **A match NetBox already holds** is proposed as the device type.
- **A match NetBox lacks** is proposed as a device type to create, with its interface templates,
  through the same confirm. That needs `dcim/device-types` and `dcim/interface-templates` writes
  through the chokepoints, recorded as created.
- **No match** is said, with the generic type as the fallback the person chooses.

**Shipped, not a development tool:**
- Mercury would read the library at run time, so a copy that ships with Mercury is listed in
  `docs/THIRD_PARTY.json` (the shipped list), never in docs/THIRD_PARTY_DEV_TOOLS.md, which holds
  only tools never shipped.
- CC0-1.0 is a public-domain dedication, not copyleft. A shipped component's licence is still the
  operator's (CLAUDE.md, Phase 7 operating mode, stop 3).
- Fetching the library online instead would be an online feature, off until configured
  (docs/PHASE8_PLAN.md section 0.3, "Mercury functions 100% locally"). The recommendation is a
  pinned local snapshot (section 14, decision 4).

### 5.5 A subnet sweep

**Probe a management subnet:**
- A TCP connect to port 22, and the SSH banner read (`SSH-2.0-Cisco-1.25` names a vendor without
  a login).
- An SNMP `get` of `sysObjectID` and `sysName` with the network's SNMP credential.
- **No login is attempted during a sweep,** so a sweep never locks an account or trips a login
  alarm.

**List what answers.**
- Grouped: answers SSH and SNMP, SSH only, SNMP only, already in NetBox (named, linked), no
  answer (counted, not listed).
- Searched by address and vendor hint.

**Then** pick, assign a site and role (per row or to all picked), and **Discover in bulk:** one
job that runs 5.2 to 5.4 for each picked address and proposes a Planned record per device, then
one review for the batch.

**The standing rules hold:**
- **No device change.** Only a connect, a banner, an SNMP get and the allowlisted reads.
- **Enterprise scale.** The sweep is a job with its progress announced, never a request.
- **Concurrent reads.** `fanout.read_each` (16 workers by default, `modules/fanout.py` L34), with
  a per-subnet rate bound.
- **Bounds.** Each connect about 2.5 times a measured connect, and the whole sweep bounded and
  named when it fires.
- **The backup window.** No sweep runs in a lab's nightly backup window (CLAUDE.md, "Standing
  facts about this lab").
- **A cap per sweep:** a /22 for IPv4 (1,024 addresses), above SolarWinds' recommended /23.
  Larger is refused, naming the size and the cap.
- **IPv6 subnets are not swept,** said by name on the screen: a /64 cannot be enumerated (section
  9).

### 5.6 Proposals, never overwrites

- **An empty field is filled** only after a preview the person confirms. The preview shows each
  field, its NetBox value (empty) and the discovered value.
- **A disagreement is shown, never resolved by Mercury.** "NetBox says device type Generic
  switch; the device reports 7050SX3-48YC8." The person chooses which side is right per field:
  - keep NetBox's, recorded as a decision;
  - take the device's, a NetBox write in the confirm;
  - or leave it open as a row.
- **Every NetBox write goes through the normal confirmation** (1.4): the plan hash, the token, the
  master switch, tagged and recorded.
- **Re-discovery reports drift.** A later read of a device is compared with NetBox, field by
  field:
  - a changed serial on the same name means a hardware swap: a Needs attention row naming both
    serials, whose action is "Accept the new serial" (a confirmed NetBox write) or "Investigate",
    and which clears when NetBox and the device agree, or by acknowledgement;
  - a changed version is a fact for History, not a row;
  - a new interface or neighbour is a proposal.

  This is NetBox Assurance's pattern, which docs/NSOT_OWNERSHIP.md part 4 already adopts
  ("Observed against intended differences are rows").

## 6. The management port

### 6.1 The Management section

It is offered in the single-device form (4.1) and the bulk columns (6.3):
- **Dedicated port.** Pre-selected from the device type's interface template marked `mgmt_only`,
  and confirmed by the person. With two such templates, the person picks one. With none, this
  choice is greyed out, saying why.
- **In-band VLAN.** Asks for the VLAN, which must exist at the site, and creates the VLAN
  interface (`Vlan<N>`, type virtual).
- **Loopback.** Creates it (`Loopback0` unless named, type virtual).

### 6.2 The management address

- **It goes on that interface** as an `ipam/ip-addresses` object assigned to it.
- **Dedicated port:** it becomes the device's OOB IP (`oob_ip`, NetBox 3.6 and later:
  https://raw.githubusercontent.com/netbox-community/netbox/main/docs/release-notes/version-3.6.md).
- **In-band (VLAN or loopback):** it becomes the device's primary IP (`primary_ip4` or
  `primary_ip6` by its family:
  https://raw.githubusercontent.com/netbox-community/netbox/main/docs/models/dcim/device.md).
- **It must lie in the site's management prefix in IPAM:** the prefix scoped to the site whose
  role is Management. That is the role Mercury's import already gives management prefixes
  (`modules/netbox_client.py` `_infer_prefix_role_name`, L788-L796), so it is an inherited
  default, not a new setting.
- **It must not already be in use** in that prefix's VRF.
- **Exactly one management address per device.** A second is refused at planning, and a record
  with two candidates is Not ready at onboarding (3.3).

**One reader, everywhere.** Which interface and address are the management ones becomes one
function with one owner (CLAUDE.md, "One owner per piece of state"). It is lifted from
`openflow_values.management_reason`: `mgmt_only`, or holding `oob_ip`, or holding the primary
IP. Its readers:
- the NetBox-sourced inventory's address (`netbox_source.adapt_devices`, today `primary_ip4`
  only): `oob_ip` when set, else the primary IP of either family;
- OpenFlow's `switch.address` and its port exclusion;
- onboarding's prefill (3.2) and readiness (3.3);
- discovery's mismatch check (6.4);
- the bounce's guard (6.5).

### 6.3 The bulk columns

| Column | Meaning | Required |
|---|---|---|
| `mgmt_interface` | the management interface's name | optional when the device type marks exactly one `mgmt_only` template (then it is that one); required for a loopback with another name |
| `mgmt_address` | the address with its prefix length (`192.0.2.11/24`, `2001:db8:0:99::11/64`) | yes |
| `mgmt_vlan` | the VLAN of an in-band management interface | only for in-band |

The kind is derived from these, never typed (CLAUDE.md, "If the safe path is tedious, people
route around it"):
- `mgmt_vlan` given: in-band VLAN;
- `mgmt_interface` a loopback name: loopback;
- otherwise: dedicated.

A row whose columns contradict each other, such as a `mgmt_vlan` with a `mgmt_interface` naming a
physical port, is refused, naming both.

### 6.4 Discovery records the interface the device answers on

Discovery reads which interface holds the address Mercury connected to (5.3), and records it in
the proposal. When the plan says otherwise, it is flagged: "edge1 answers Mercury on Vlan99
(192.0.2.11); its plan's management interface is Management1". The person corrects the plan or the
device. Mercury fixes neither silently.

### 6.5 Elsewhere in Mercury

**OpenFlow (built).** The OpenFlow templates always exclude the management interface:
`openflow_values.management_reason` (1.6), Lab 9's piece 2 at `1e9b4bef`. **What changes:** only
that `management_reason` moves to the one reader (6.2), with its behaviour unchanged.

**The port-bounce guard (designed, not built).** It refuses the management interface directly,
beside the CEF check. **What changes:** guard 13c (docs/HEAL_TO_INTENT.md 19.4; N17 in 19.10)
gains a check (0), before the device is read:
- **Check (0).** "Not bounced: NetBox marks Management1 as edge1's management interface
  (`mgmt_only`)", or "(it holds edge1's OOB IP 192.0.2.11)", or "(it holds edge1's primary IP)".
  It is read from NetBox through the one reader, plus the device environment's reserved
  interfaces.
- **Why it comes first.** It needs no device session, so it refuses even when the device cannot
  answer. It catches a dedicated management port that is not the interface Mercury reaches the
  device on today. Checks (1) to (3) cannot see that port: each reads the path Mercury uses now.
- **Checks (1) to (3)** stay as written, and 13f's revert timer is unchanged.
- **Where it is added:**
  - the revert probe's `path_refusal` (`scripts/nmas-revert-probe` L385), whose 13c reading is
    C2464's;
  - H20's module, when it builds 13c, from the same reader.

## 7. The screens, each needing a board

Every screen needs a board, signed off before it is built (CLAUDE.md, "No new screen or tab
without a mockup"; `tests/signed_off_screens.py`). Each board draws every control and link,
including the not-ready links (3.3) and the confirm.

| Board | Screen | Where |
|---|---|---|
| NP1 | Add device from NetBox: the Planned list, summary, groups, filters, search, multi-select, the method choice, Not ready with its links | Devices › Add device (replaces today's typed form as the first view; the typed form stays for a local list with no NetBox) |
| NP2 | Bulk onboarding: the dry-run summary, the one confirm, the batch run, the end-of-batch seeding and break-glass | the batch run view (boards B and K's stepper) |
| NP3 | Plan devices, one device: the form, the device type's templates read-only, the Management section, the preview and confirm | Source of Truth › NetBox › Plan devices |
| NP4 | Plan devices, bulk: upload, column mapping, validation, row-by-row preview, confirm, results per row | the same page's Bulk tab |
| NP5 | Discover a device: the minimal record, the detection result, the proposal (fill, disagree, the device type match, the answering interface, the host-key fingerprint) | Plan devices › Discover |
| NP6 | Subnet sweep: the subnet, the answers grouped, pick and assign, Discover in bulk | Plan devices › Discover, its Sweep tab |
| NP7 | Drift on re-discovery: the Needs attention row and its detail (serial changed, the fields that disagree) | Needs attention; the device's NetBox tab |

**The manual.** A page per screen and a How it works page per operation (`plan`, the bulk
upload, discover, sweep, bulk onboarding), each step named as its code declares, with a diagram
(CLAUDE.md, "The manual covers every screen and operation").

## 8. Large fleets

- **Every list leads with counts by outcome:** Planned (ready, not ready, being onboarded),
  upload rows (create, update, unchanged, refused), sweep answers, discovery proposals.
- **Every list groups and collapses,** filters by site and role, and searches by name, address and
  serial. A subset is said.
- **No list draws one long expanded list.** `tests/test_large_fleets.py` covers each new list at
  its 900-device scale.
- **No per-device work per request.** The Planned list is a reader's stored value. Sweeps, bulk
  discovery and bulk onboarding are jobs (CLAUDE.md, "Enterprise scale").
- **Every NetBox read is paginated to its end** (`_nb_get`, L262) and never stops at a page. A
  read that returns exactly its page size is treated as truncated (CLAUDE.md, "A read returning
  exactly its page size is truncated"). `fetch_netbox_devices`' `limit=500` is a page size, not a
  cap, because `_nb_get` follows `next`.

## 9. IPv6 parity

Every feature is built and tested with an IPv6 case beside its IPv4 one (CLAUDE.md, and
docs/IPV6_PARITY.md):
- **The management address** may be IPv6: `primary_ip6` in-band, or `oob_ip`. The one reader
  (6.2) closes `netbox_source`'s `primary_ip4`-only break site (C1245).
- **Validation** uses `ipaddress.ip_interface` for both families. The management prefix is
  looked up in the address's own family.
- **Discovery** reads IPv6 interface addresses, and LLDP management addresses of either family.
- **The subnet sweep cannot enumerate an IPv6 subnet,** and its screen and manual page say so by
  name. IPv6 devices are found instead from:
  - neighbours: LLDP management addresses, a router's `show ipv6 neighbors`;
  - DHCPv6 leases, after C1245's DHCPv6 path.
- **The out-of-band console path** stays IPv4-only, said, as today (`oob_onboard._planned_address`).

## 10. DECISION and LABOUR (docs/MANUAL_STEPS.md)

| Step | Kind | Why |
|---|---|---|
| Choose a device's site, role and device type when planning | DECISION | what should exist is a person's design |
| Choose the management kind (dedicated, VLAN, loopback) and its address | DECISION | the design of the management network |
| Confirm a plan, an upload or a discovery proposal by its hash | DECISION | M1 |
| Choose which side is right when discovery and NetBox disagree | DECISION | the source of truth changes only by a person |
| Accept a new serial after a hardware swap | DECISION | a swap is a claim a person makes |
| Choose an onboarding method | DECISION | depends on how the device is cabled and boots |
| Confirm the column mapping | DECISION, once per file shape | a mapping is a claim about the file; saved, so it is not repeated |
| Type a device's interfaces | removed | from the device type's templates |
| Type the management address, MAC and interface into Add device | removed | prefilled from NetBox (3.2); today's M-row for it is replaced |
| Type a device's model, serial, version | removed | discovered (5.3) |
| Open NetBox to fix a Planned record | removed | Plan devices' links (3.3); NetBox stays for audit (C1445) |
| Map a NetBox platform to a driver in Platforms and roles | DECISION, once per platform | which driver a platform uses is a person's |
| Add a credential profile covering the devices | DECISION (which profile) and the secret typed | secrets are typed by a person (Credentials) |
| Turn NetBox writes on in a fresh install | DECISION, today LABOUR | C2548's control removes the labour |

The new rows enter docs/MANUAL_STEPS.md when each piece is built, in the commit that builds it.

## 11. Wrong things that would look right

| Looks right | Is wrong | What makes it visible |
|---|---|---|
| A Planned device listed as Ready | its one address is outside the site's management prefix | readiness checks the prefix as planning does; the reason is named |
| An upload preview with all rows Create | half are duplicates of records in another site of the same name | the name check covers the network's whole NetBox scope, and names the holder's site |
| A discovered "model" filled in | the template parsed the wrong field on an unfamiliar image | each fact shows its command and the capture it came from, one click down |
| A device type matched from the library | the part number matched two models | two matches are refused as ambiguous, both named |
| A sweep that "found nothing" | SNMP's credential was wrong and SSH is filtered | the sweep reports SNMP auth failures and timeouts apart from no answer |
| Re-discovery quiet | the reads failed | an unreadable re-discovery is its own row, never "no drift" |
| The bounce allowed on a port | NetBox marks it the dedicated management port, though Mercury uses in-band today | check (0) refuses from NetBox before the device is read |

## 12. The tests a build must hold

- **Planned list:** a Planned record is listed once, and a record with a manifest entry is not
  listed. Each Not-ready reason has its own case. A NetBox read that fails is a row, never an
  empty list. 900 records pass the large-fleets test.
- **Prefill:** each prefilled field equals NetBox's value. An IPv6 management address prefills
  as IPv6. A record with two candidate addresses is not ready.
- **Plan (single):** the preview's objects equal the dry run's writes, and the confirm refuses a
  moved plan, naming both hashes. A taken name is refused, naming its status. Interfaces are
  never in the payload, which holds only the device and the management objects. Both families
  are tested.
- **Bulk upload:**
  - each validation failure is named with row, column and both operands;
  - a credential-looking header is refused;
  - a re-upload updates and never creates a second record;
  - an `id` column renames;
  - nothing is written while a row is refused;
  - an `.xls` is refused by format;
  - an oversize file is refused before parsing;
  - the History record holds the file's hash, never its text.
- **Discovery:**
  - the probe sends only its positive list: a fake session records every write, and an unlisted
    command fails the test;
  - SSHDetect is never imported by product code (a scan);
  - every parser runs on a real capture fixture, never typed text;
  - every answer is masked before it is stored;
  - a disagreement produces a choice, never a write;
  - a serial change produces a Needs attention row whose clears are tested.
- **Sweep:**
  - no login is attempted (the fake records no authentication);
  - the /22 cap is refused above it;
  - an IPv6 subnet is refused by name;
  - the job's bound names what ran.
- **The management reader:** one function, and a scan shows no second definition. OpenFlow's
  exclusion is unchanged. The inventory reads `oob_ip`, then the primary IP of either family. The
  bounce's check (0) refuses with no device session.
- **Every new check is shown able to fail** (CLAUDE.md, "Every new check is shown able to fail").

## 13. The estimate, and the order

The estimate uses the measured ratio: one agent-day is about 1.3 wall-clock hours (0.7 to 2.6)
and about 4M weighted tokens (2.5M to 9M) (docs/PHASE8_PLAN.md section 0.3). Each piece includes
its tests and its manual page. Boards are counted apart.

| Piece | What | Agent-days |
|---|---|---|
| S1 | **Early split:** C2553's evidence and the import's stale docstring corrected; `_parse_device_facts` removed (no caller) | 0.2 |
| S2 | **Early split:** the one management reader (6.2), read by the inventory (`oob_ip`, IPv6), OpenFlow and the revert probe's check (0) | 1.0 |
| S3 | **Early split:** C2548, turning NetBox writes on in Mercury (its own board) | 1.0 |
| P1 | Add device from NetBox: the Planned reader, readiness, the list, prefill into the single-device plan | 3.0 |
| P2 | Plan devices, one device: the `plan` operation, the Management section, IPAM checks, History | 3.5 |
| P3 | Plan devices, bulk CSV: template, mapping, validation, preview, confirm, results, re-upload | 4.5 |
| P4 | Bulk onboarding from the list: the dry run, the batch, end-of-batch seeding and break-glass | 4.0 |
| P5 | Discover a device: the probe, the fact reads and parsers for the listed families, the device-type mapping, proposals | 6.0 |
| P6 | Re-discovery drift: the job, the Needs attention row, its clears | 2.0 |
| P7 | Subnet sweep: the job, bounds, the grouped answers, bulk discover | 3.0 |
| P8 | The `.xlsx` reader, once its licence is approved | 1.0 |
| B | Boards NP1 to NP7 and their fidelity records (about 0.4 each) | 2.8 |
| | **Total** | **32.0** |

**About 42 wall-clock hours** (22 to 83) and **about 128M weighted tokens** (80M to 288M).

**What can be split out early:**
- **S1:** a docs-and-dead-code commit.
- **S2:** it fixes a real break site today, a dedicated-port or IPv6-only device skipped by the
  NetBox inventory, and gives Lab 9's OpenFlow and Lab 10's bounce one reader.
- **S3:** C2548, a B row already, blocking every fresh install's first onboarding.

None of the three needs a new screen except S3's control.

**The recommended order:**
1. **S1, S2, S3.**
2. **Boards NP1, NP3, NP4.**
3. **P1:** the main path. It works at once with records made by NetBox's own import.
4. **P2:** shares P1's readiness rules.
5. **P3:** reuses P2's validation.
6. **P4:** after both single paths are walked.
7. **Boards NP5 to NP7.**
8. **P5:** its parsers want Lab 9's real captures as fixtures.
9. **P6.**
10. **P7:** after discovery works on one device.
11. **P8:** when the licence is decided.

Nothing here starts before both labs, except what the operator moves forward.

## 14. Decisions for the operator

Only what practice does not decide. Each carries a recommendation.

1. **A dedicated port's address:** `oob_ip` only, with Mercury's one reader reading `oob_ip`
   first; or both `oob_ip` and the primary IP set to it. **Recommended: `oob_ip` only,** as the
   design says. One fact, one field, one reader.
2. **Planning's writes:** direct through the chokepoints now (new objects, tagged, recorded,
   removable); or wait for NetBox Branching (docs/NSOT_OWNERSHIP.md, "Before Phase 2"). The
   ownership decision requires branching for design data on managed devices, and a Planned
   record is not one yet. **Recommended: direct,** an exception that expires when the branching
   spike is measured.
3. **The `.xlsx` reader:** openpyxl (MIT, shipped, so the operator's licence decision).
   **Recommended: CSV first, openpyxl approved when P8 is built.**
4. **The devicetype-library (CC0-1.0):** a pinned snapshot shipped with Mercury (listed in
   `docs/THIRD_PARTY.json`); or fetched online, off until configured. **Recommended: the pinned
   snapshot,** so it works offline.
5. **SNMP for detection:** through the deployment's snmp_exporter probe (no new library); or
   pysnmp (a new shipped dependency). **Recommended: snmp_exporter,** after a probe of one
   device shows its `system` module answers a target that is not yet scraped.
6. **Planned records in a NetBox-sourced network's inventory:** today a network whose filter
   names no status loads Planned records as devices (`fetch_netbox_devices` applies `status` only
   when given, L91-L95). Lab 9's kit relies on that for its read-only switches. **Recommended:
   a device is "in Mercury" only by onboarding or adoption.** The inventory leaves Planned
   records out by default, and a network may list them read-only for discovery drivers, said on
   its pages.
7. **The gateway for prefill:** NetBox has no gateway field on a prefix. Options: the address
   tagged `gateway` in the management prefix, or a custom field on the prefix. **Recommended: a
   custom field `gateway` on the prefix,** read-only to Mercury, its absence leaving the gateway
   asked.

## 15. Rows for the register

The register was searched first for each: C2553, C2548, C2527, C1245, C676, C1574, C559, C556,
C759, C2464, C1006. Recorded 2026-11-05 in docs/OPEN_FINDINGS.md: R1 as C2553's corrected
evidence, and R2 to R8 as C2561 to C2567, in that order. The register's rows are the ones that
stand; the notes below are the design's reasons for them.

- **R1, a correction to C2553:** its evidence names a live `show version` and `show inventory`
  scan and `_parse_device_facts`.
  - What the code does: that function has no caller, the facts come from goldens by
    `_parse_facts_from_config` (manufacturer `Cisco`, model `Unknown`, serial empty), and the
    only live SSH is the CDP and LLDP neighbour read (`modules/netbox_client.py` L1893, L3143,
    L1959).
  - The conclusion (Cisco-only) stands. The bucket is unchanged.
- **R2, C:** `modules/netbox_client.py`'s docstring (L9-L11) says every device is scanned by SSH,
  which Stage 3.3 removed (L1946-L1957), and `_parse_device_facts` (L1893) is dead.
  - Area: integrations. Phase 8: after.
  - Evidence: the lines named, and a whole-repository search for the function.
  - Nearest rows: C2553, C559.
- **R3, B** (blocks bulk onboarding from NetBox, docs/NSOT_STAGE10_PLAN.md 7.3): Add device has
  no list of Planned records. The name is typed and matched (`templates/v2/_onboard_add.html`
  L57-L58), and the management address, mask, MAC and interface are typed (L76-L85) although
  NetBox holds them. That typing is LABOUR.
  - Area: onboarding. Phase 8: after.
  - Nearest rows: C676, C1574, C2527.
- **R4, C:** the charter's entry point 2 says a device created in Mercury is written into NetBox
  first as Planned. Create writes nothing in NetBox, and the record is created at Verify from the
  first capture (`modules/nsot/onboard.py` L381-L383, L1651).
  - Area: onboarding. Phase 8: after.
  - Nearest rows: C556, C2548.
- **R5, B** (blocks the dedicated-port management design, section 6): the NetBox-sourced
  inventory reads `primary_ip4` only (`modules/inventory/netbox_source.py` L130-L134), so a
  device whose management address is its `oob_ip`, or IPv6, is skipped.
  - Area: integrations. Phase 8: after.
  - Nearest rows: C1245.
- **R6, UNKNOWN:** the import writes an interface's `mac_address` (`modules/netbox_client.py`
  L1136-L1164), and NetBox 4.2 moved MAC addresses to an object of their own (to confirm).
  Whether 4.6 stores, ignores or refuses the field is unmeasured; ignored would be data silently
  lost, so it could be A.
  - The one measurement: import one device into a 4.6 NetBox and read its interface's MAC back.
  - Area: integrations. Phase 8: after.
  - Nearest rows: C559.
- **R7, C:** a NetBox-sourced network loads Planned records as devices when its filter names no
  status (`modules/inventory/netbox_source.py` L91-L95), so "in Mercury" has two meanings
  (section 14, decision 6).
  - Area: NSoT/devices. Phase 8: after.
  - Nearest rows: C556.
- **R8, B** (blocks shipping the bounce as the operator's design of 2026-11-05 requires): guard
  13c has no NetBox-declared management interface check. The revert probe's `path_refusal`
  (`scripts/nmas-revert-probe` L385) reads only the device's own address and CEF egress.
  - Area: operations. "Lab 10: blocks" if the bounce ships for Lab 10, else Phase 8: after.
  - Nearest rows: C2464, C2463.

## 16. Claims not verified here

- That NetBox's bulk import instantiates the device type's interface templates. The model
  documentation says a device inherits them "at the time of creation", and an import saves the
  model, but no page states it for the import. To confirm on the kit's NetBox.
- **The NetBox source read was the `main` branch's, not the 4.6.10 tag's.**
  - That 4.6.10's IP address import form takes `is_primary` and `is_oob`, and its device form the
    fields named in 4.2, was read from the kit image's forms for the sitting's import sheets. It
    was not re-read here.
  - That NetBox 4.2 made MAC addresses an object of their own (R6) is from memory.
- That `oob_ip` and a primary IP may name the same address object (decision 1's alternative).
- That snmp_exporter's probe endpoint answers a target it does not already scrape, with an auth
  from its configuration (decision 5).
- What netmiko's `autodetect` device type opens as a session class under `open_ssh`, and whether
  a probe before paging is turned off reads a whole `show version` first screen.
- Forward Enterprise's CSV import, subnet scan and CDP or LLDP seeding: its community page refused
  the fetch.
- Whether the Device-Type-Library-Import script updates types it finds (only that it skips them
  is stated).
- The commands marked **(to confirm)** in 5.3: `show ipv6 interface brief`'s template, NX-OS's
  `show ip interface brief`, EOS's `show hostname`, ProCurve's `show ip`, AOS-CX's `show module`.
- That pysnmp's later releases keep the `oneliner` API netmiko's SNMPDetect imports (lextudio's
  changelog suggests it moved).
- Every probe and sweep bound: none is measured. Each is measured on s1 and r2, outside the backup
  window, when built.
