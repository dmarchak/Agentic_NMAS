# Ownership: every piece of device state, its one owner, and who may write it

The operator's decision, 2026-10-07: **NetBox is the source of truth for DEVICES**: their
existence, role, site and status (Active, Drained, Planned, …). Mercury owns intent and the
record of what was done. Measurements own what is observed. Each piece below has exactly ONE
owner. Mercury may show a piece it does not own, always with its source and its age, and may
write it only where the "writes" column says so.

Part 1 is the map, as decided. Part 2 is what changes when networks are NetBox-sourced by
default, APPROVED IN SHAPE 2026-10-07 with its five decisions; nothing in it is built. Part 3 is
Default's census.

## Part 1. The map

### The device itself

| Piece | Owner | Who writes it | Mercury today |
|---|---|---|---|
| **Existence** (the device is in the network) | **NetBox** | a person in NetBox; Mercury's onboarding and adopt, as a confirmed step | a local list's `devices.csv` owns it, and onboarding creates the NetBox record (r2's); see Part 2 |
| **Name, role, site, platform** | **NetBox** | a person in NetBox | read from the inventory (CSV or NetBox per list) |
| **Status** (Active, Planned, Drained, Decommissioning, …) | **NetBox** | a person in NetBox; Mercury only inside a confirmed runbook step (drain, return to service, retire), through the write chokepoints, the before recorded | not read; Drained is designed in [NSOT_DRAINED_DESIGN](NSOT_DRAINED_DESIGN.md) |
| **Management address** | **NetBox** (`primary_ip4`/`primary_ip6`) | a person in NetBox; onboarding as a confirmed step | the CSV's `ip` for a local list |
| **Credentials** (accounts, passwords, enable) | **Mercury** (the credential store and profiles) | rotation, onboarding and a person in Credentials; never NetBox | as now: the device override, then the designated list, role, site, then the default profile |

### Configuration

| Piece | Owner | Who writes it | Notes |
|---|---|---|---|
| **Intent** (`host_vars/<device>.yml`) | **Mercury's intent git** | an intent commit (the editor, seed, bulk intent, a runbook step), as a verified person | |
| **Templates and their approvals** | **Mercury's intent git** | template approval and revocation | |
| **Golden** (the last measured running config) | **Mercury's intent git** | `save_golden()` only (capture, Save All, a deploy's and restore's read-back) | |
| **Baselines, golden-state tags** | **Mercury's intent git** | earned by measurement, never set | |
| **Running config** | **the device** | deploy and restore (the pipeline); the console is outside the record | observed by capture and Save All |
| **Oxidized's copy** | **Oxidized** | Oxidized's polls; Mercury asks it to fetch | a cross-check (freshness), never truth (C555) |
| **Interfaces, IP addresses, VLANs, VRFs in NetBox** | **Mercury's intent**, mirrored into NetBox | the NetBox import, tagged and recorded as created, the before of an update recorded | documentation in NetBox, derived from goldens; a decision point in Part 2 |
| **Customer prefixes** (a prefix role) | **NetBox** | a person in NetBox | the drained measurement reads them |

### Observed state (measurements)

| Piece | Owner | Read by |
|---|---|---|
| Reachability | the reachability reader | Devices, the device page, Needs attention |
| Restarts | the restarts reader (Prometheus `sysUpTime`) | History, Needs attention |
| Monitoring data, alerts | Prometheus, Loki, Grafana | Monitoring, Needs attention |
| Customer traffic (drained) | the drained measurement (designed) | the Service panel, compared with NetBox's status |
| Lab startup files, freshness, drift | their readers and the drift checker | Needs attention |

### Mercury's records (Mercury owns, nobody else writes)

| Piece | Where |
|---|---|
| Receipts, rollback blocks, retry authorisations | the network's `.nsot/` and data folder |
| Rotation record, break-glass log, persist records | the data folder |
| Acknowledgements, planned-restart windows, known-noise classifications | the network's data folder |
| Approvals queue, NetBox write provenance | the data folder |
| Runbook runs (designed) | the network's record |

### Generated from the above (never edited by hand)

| Piece | Generated from | By |
|---|---|---|
| Prometheus targets | the inventory | `prometheus_targets` |
| Grafana rules and dashboards | the monitoring templates and the inventory | monitoring templates |
| The counting ACL (designed) | NetBox's customer prefixes | the drained measurement's template section |
| Lab startup files | the newest earned baseline and current credentials | the clab sync (lab tooling) |

## Part 2. NetBox-sourced by default (approved in shape 2026-10-07; not built)

**Today.** Each network's inventory is `local` (a CSV in Mercury) or `netbox` (read from
NetBox), and Default is local. Onboarding writes the device into the CSV AND creates its NetBox
record, so Mercury owns existence and NetBox follows. The decision above inverts that.

**Proposed.** A new network is NetBox-sourced unless it says otherwise. A local list stays as
the declared exception, for a lab or an installation without NetBox, and says so on its pages.

| Area | Today | NetBox-sourced by default |
|---|---|---|
| **The device list** | the CSV, or a NetBox query per list | one NetBox query per network (its filter: site, tenant or tag), read by a reader on an interval and on NetBox's change, never per request (the scale rule). When NetBox is unreadable, the last good list stays, dated, with "NetBox unreadable since"; writes are refused |
| **Onboarding** | creates the CSV row and the NetBox record | starts from a NetBox device in status **Planned** (a person creates it in NetBox, or onboarding's first step does, as a confirmed write); success sets **Active** (a confirmed write, the before recorded). The ZTP and DHCP paths take the device's management address from NetBox |
| **Adopt** | creates the CSV row; records what already existed in NetBox as adopted | requires the NetBox device (or creates it as a confirmed step); adopt sets **Active** |
| **Retire** | drops Mercury's records, deletes NetBox objects it created and tagged | sets NetBox's status to **Decommissioning** (confirmed), drops Mercury's records; deleting the NetBox device stays a person's act in NetBox (Mercury deletes only what it created, tagged and recorded) |
| **Credentials** | per device, list, role, site, default | unchanged and never in NetBox; role and site come from NetBox |
| **Platform** | the CSV's platform or Mercury's resolution | NetBox's platform slug, through one mapping table (one owner, the platform-keying rule) |
| **Interfaces and addresses in NetBox** | Mercury imports them from goldens (Mercury writes) | **a decision**: keep the import (Mercury's intent mirrored into NetBox, as now), or let NetBox own IPAM and render intent from it (NetBox as the source of the network's design, a larger change) |
| **The local list** | the default | the declared exception: its pages say "local list: no NetBox", and the lab-specifics rule keeps lab-only behaviour out of the product |
| **Default, today's network** | local | moved once, by a census: every CSV device must match a NetBox device by name and management address, and Mercury refuses the switch, naming each mismatch, until they agree |

**Decided (the operator, 2026-10-07; approved in shape):**
1. **Planned → Active is the onboarding contract.** The NetBox device is made by a person, or
   by onboarding's first confirmed step.
2. **Retire sets Decommissioning only.** Deleting the NetBox device stays a person's act in
   NetBox.
3. **Mercury's interface and address import into NetBox stays**, for now. NetBox-owned IPAM is
   a later, separate change.
4. **The network's NetBox filter is a tag by default**, with site as the alternative.
5. **Default's census runs NOW**, read-only, reporting the mismatches (part 3). Default moves
   after Stage 7's cutover.

## Part 3. Default's census (read-only)

Every device in Default's local list against NetBox, by name and management address, so the
move after cutover starts from a known list of mismatches. Read on the host on 2026-10-07
(GETs only; the live checkout unchanged):

| Check | Found | What the move needs |
|---|---|---|
| Name and management address | **9 of 9** local devices match a NetBox device | nothing |
| In NetBox, not in the local list | **r5**, status **Active** | r5 was retired in Mercury before the retire contract: its status set to Decommissioning (a person in NetBox, or retire's confirmed step once built) |
| Platform | NetBox says `ios` for all ten; Mercury knows r1 to r4 and r6 as `cisco_iosxe` | NetBox's platform corrected for the five IOS-XE routers, and the mapping table (one owner) from NetBox's slug to Mercury's platform |
| The network's tag (the decided filter) | none: no device carries a network tag (r6 alone has `nmas-managed`) | a tag for Default created and set on its nine devices |
| Role, site, status | routers and switches by role, all in site `default`, all Active | nothing |

The census is repeated read-only before the move; the move refuses while any row above
still needs something.

**Repeated 2026-10-07, after the operator's NetBox fixes (with `a3685bc` on the host): NetBox
matches.** All nine devices match by name and address, are Active, and carry
`nmas-network-default`. Their platforms resolve through Mercury's one mapping table to the
dialect Mercury holds: `cisco-ios-xe` → `cisco_iosxe` for r1 to r4 and r6, `cisco-ios` →
`cisco_ios` for s1 to s4. r5 is in NetBox only, Decommissioning and untagged. Left to watch:
that the next NetBox sync leaves the platforms as they are (C557).

**What Mercury's sync writes on a device today**, read in the code on 2026-10-07 before the
operator's NetBox fixes:
- **Platform:** was rewritten on every sync from a config-text guess, which is why every
  device reads `ios`. It stops with `a3685bc` (C557): an update no longer sends it.
- **Status:** create-only since 2026-09-24.
- **Tags:** a union with the device's own; a tag a person adds is never removed.
- **Device type:** was rewritten on every sync as "Unknown" (the import from goldens never
  knows the model). It stops with the C559 commit: an update no longer sends it.
- **Still rewritten on every sync:** `name`, `role`, `serial`, `comments`,
  `primary_ip4`/`primary_ip6`, `config_template` and `local_context_data` (the config context:
  the sanitised running config and facts). These are Phase 1's to stop (Part 4).
- **The primary IPv4 is set to the management address**, measured 2026-10-07: every Default
  device's `primary_ip4` is its 10.255.x management address. NetBox's `primary_ip` showed the
  IPv6 loopback only because `PREFER_IPV4` is off (C560; the host step is in
  [NSOT_DRAINED_DESIGN](NSOT_DRAINED_DESIGN.md) section 8).

**Until Phase 1, people must not edit a managed device's name, role, serial, comments,
primary IP addresses, config template or config context in NetBox:** the next sync overwrites
each of them. Platform, status, site and tags are safe to edit now, and device type once the
C559 commit is on the host.

## Part 4. The direction of data (APPROVED 2026-10-07)

NetBox becomes the source of truth by a deliberate migration, never by a switch. Each field has
ONE owner and ONE writer, and data flows NetBox → Mercury → devices. Each phase turns off the
old writes for the fields it moves, in the same change that moves them.

### The phases

| Phase | Fields | NetBox | Mercury | Turns off |
|---|---|---|---|---|
| **Bootstrap** (done) | everything the import knew | filled by Mercury's import from the devices | wrote them | nothing yet |
| **Review** (now) | identity | made correct by a person, from the census (part 3: r5's status, the platforms, the network tag) | reads the census, read-only | the platform rewrite (`a3685bc`) |
| **Phase 1, identity** | existence, name, role, site, platform, status, management address | owns them | READS them: the NetBox-sourced inventory (part 2) | every sync write of those fields (`name`, `role`, `primary_ip4`/`primary_ip6`; site, status, platform and device type already off) |
| **Phase 2, design data** (decision 3, deferred) | interfaces, addresses, VLANs, VRFs | owns them, once decided | GENERATES that part of intent from NetBox's data (the style of Nautobot's Golden Config and NetBox's config templates), and compares the device against it | the interface and address import, which until then continues, marked "documentation, derived from the devices" |
| **Phase 3, discovery as proposal** | what Mercury finds on a device that NetBox lacks (a new interface, a neighbour, a serial) | receives a PROPOSED change, approved by a person (Diode-style ingestion into a branch or changeset) | proposes, never writes directly | any remaining direct write from discovery |

### The write pattern: the source of truth leads

Mercury writes to NetBox **only as the FIRST step of a confirmed operation**, never as an
after-the-fact sync:

1. **The preview shows both sides:** the NetBox change (field, before, after) and the device
   program. The confirm's hash covers both.
2. **On confirm, the NetBox change is made first,** in a NetBox Branching branch
   (`netbox-branching`, NetBox Labs; it requires NetBox 4.1 or later, and ours is 4.6.9).
   **Branching is REQUIRED for design-data writes** (Phase 2). A direct write, with its before
   recorded (today's provenance), is acceptable only for a single-field status transition:
   Drained, Active, Decommissioning, and Planned → Active.
3. **The devices change from it**, with verify and rollback, as every operation does.
4. **On success the change becomes official** (the branch merged). **On failure it is undone**
   (the branch abandoned, or the before restored), so NetBox never claims what is not true.
5. **NetBox's change-log entry and Mercury's receipt link to each other:** the receipt names
   the change-log entry or branch, and the change's comment names the receipt.

It applies to:
- retire (Decommissioning);
- drain and return to service (Drained, Active);
- onboarding (Planned → Active);
- after Phase 2, intent edits of NetBox-owned design data.

**Observed against intended differences are rows,** as NetBox Assurance reports deviations:
NetBox says Drained while traffic flows, NetBox's platform against what the device reports, an
interface in NetBox the device lacks. They are never fixed silently, in either direction.

**NetBox may START Mercury's planning:** an Event Rule (a webhook on a device's or interface's
change) asks Mercury to prepare the operation's preview for a person. It never applies
anything.

### Before Phase 2: a measured spike of the branching plugin

Before design data moves, a spike on a copy of this NetBox measures:
- the install (the plugin, its database schemas, the upgrade path with netbox-docker);
- the API (creating a branch, writing in it with its header, reading main and branch);
- merge and revert (what a merge conflicts on, whether a merged branch can be reverted, and
  what each leaves in the change log);
- the cost (a branch per operation at fleet scale).

Each finding is recorded, and the design is revised from it.

**Decided (the operator, 2026-10-07):**
1. **Phase 1 comes after cutover.**
2. **Branching is REQUIRED for Phase 2's design-data writes.** A direct write with its recorded
   before is acceptable for single-field status transitions: Drained, Active,
   Decommissioning, and Planned → Active.
3. **Event Rules start planning for:**
   - a managed device's status change: Drained → a drain plan; Active after Drained → a
     return plan;
   - a device created as Planned → an onboarding plan;
   - in Phase 2, design-data changes on managed devices.

   Each always ends in a preview a person confirms, never an apply.
