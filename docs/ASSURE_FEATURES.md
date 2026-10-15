# Assure: three proposed features

Recorded 2026-10-15 at the operator's request, for the plan. **Nothing here is built.** Each
is a proposal for Stage 9, registered as a C row (C799 to C801, C803 to C806 in
[OPEN_FINDINGS](OPEN_FINDINGS.md)), and judged against the
[charter](MERCURY_CHARTER.md) before any design work starts. They extend Assure as
[IBN_DESIGN](IBN_DESIGN.md) section 1 ("Assure: verify continuously") and section 2 describe it.

The shared dependencies, named once:
- **E18, the records database** ([NSOT_PHASE4_RECORDS_POSTGRES](NSOT_PHASE4_RECORDS_POSTGRES.md)):
  every history below is a history, and today each reader keeps one overwritten value.
- **C764, feature packs**: per-feature intent, rendered per platform, with presets. A device-side
  setting these features need is a pack, never a line typed into intent.
- **E5, the role model** (roles and separation of duties): who may see raw evidence, per-user
  traffic, or start a test that loads a circuit.
- **Phase 8's responder** ([PHASE8_PLAN](PHASE8_PLAN.md) section 8.1): each feature names its
  natural-language hook. The AI proposes a query or a scope; the deterministic builder (E3, F3)
  reads it back before anything runs; nothing the AI writes is evidence.

## 1. Incident evidence export

**What it does.** A person scopes a time window and a set of devices, and gets one archive of
everything Mercury and its sources of truth recorded about them in that window:
- Loki's syslog and traps (by the `device` label, with `severity` and `trap_oid`);
- the network repository's commits and diffs (goldens, intent, templates);
- Mercury's own audit records: deploy receipts, acknowledgements, approvals, restart windows
  (E18 once it holds them);
- Kea's lease history for the devices' segments;
- NetBox's changelog for the devices and their interfaces and addresses;
- Grafana's alert history (state changes) for rules that name the devices.

**The archive.** A manifest (what was asked, what each source answered, what could not be read
and why), a SHA-256 per file, and an export record kept by Mercury (who, when, the scope, the
manifest's own hash). Secrets are masked by default (Mercury's `redact_text`, as every surface
is); a raw export needs an admin and a stated reason, recorded with it. A source that could not
be read is named in the manifest, never silently absent.

**Legal hold.** The objects in scope (the archive, and the MinIO lake's raw objects for the
window) are placed under MinIO Object Lock retention, so they cannot be deleted or overwritten
until the hold is released. Object Lock must be enabled when a bucket is created; whether
Mercury's bucket has it is to be measured, and if not, a hold bucket is created for it (the
operator's step).

**Evidence readiness, per device.** A check that a device's own records would stand up: its
clock NTP-synchronised; its logging level sends what an investigation needs; timestamps with
milliseconds; the archive of configuration changes (`archive log config`) and AAA command
accounting on. Each missing setting is offered as a **C764 feature pack** ("evidence
readiness"), previewed and deployed like any other operation.

**Depends on:** E18 (audit records and the export record), C764 (the readiness pack), E5 (raw
export for an admin only), MinIO Object Lock (a bucket setting, the operator's).
**Phase 8 hook:** "gather what happened on r3 between 02:00 and 02:30" becomes a proposed scope
(devices and window) that the person confirms before the export runs.

## 2. ISP circuit verification

**What it does.** For each circuit NetBox records (NetBox Circuits: provider, circuit id,
committed rate, the terminating interface), Mercury proves the provider delivers what the
contract says:
- **throughput**, by scheduled tests out of hours from an **edge test agent**, a small host at
  the edge, never the NMAS host (a test through the manager measures the manager);
- **shaping**, by a plateau in the interface's SNMP counters at or near the committed rate
  under load, read from Prometheus;
- **latency, jitter and loss**, from IP SLA probes against the contract's figures (the probes
  already scraped, C764's IP SLA pack for the configuration);
- **availability**, from link state and BGP session state over the month;
- **a monthly report card per circuit**: each figure against its contract, and every breach
  with its time and its evidence (which can be a feature 1 export).

**In the lab**, the edge uplink with a shaping policy stands in for an ISP. Every lab C8000v
forwards at most about 10 Mbit/s (CLAUDE.md, standing facts), so the stand-in's committed rate
must sit well below that, or the test measures the router's licence limit.

**Depends on:** E18 (the month's history), NetBox Circuits populated (a source of truth, the
operator's data), the edge test agent (a new component, host and schedule), C764 (the IP SLA
and shaping packs), E5 (who may start a test that loads a circuit).
**Phase 8 hook:** "is the branch's circuit delivering what we pay for?" becomes the
circuit's report card, and the query behind each figure read back by the builder.

## 3. Bandwidth by application and user

**What it does.** Which applications and which users use the bandwidth, from flow records:
- a **flow collector** on the NMAS host (GoFlow2, for example; its licence is checked before it
  is adopted, a new third-party licence being the operator's decision); raw flows to the MinIO
  lake with a retention; top-N aggregates to Prometheus for dashboards;
- **application names** from NBAR2 through a **C764 feature pack** (flow export with NBAR2
  fields), after measuring that the lab's C8000v images support it;
- collection on **LAN-side interfaces**, inside NAT, so a flow's address is a host, not the
  NAT pool;
- **IP → MAC → hostname** from Kea's lease history at the flow's time (an address is a host
  only for the lease that held it), and **users** from 802.1X/RADIUS accounting or Authentik
  when present;
- **aggregate by default**; per-user detail is role-gated (E5) and every view of it is audited.

**Depends on:** E18 (lease history by time, the audit of per-user views), C764 (the flow and
NBAR2 pack), E5 (per-user detail), the MinIO lake's retention, and a licence decision.
**Phase 8 hook:** "what used the WAN at 14:00?" becomes a top-N query over the window,
aggregate unless the person's role allows per-user detail.

## 4. Scans

**What it does.**
- **On demand:** nmap from the Toolbox (C762), a structured tool whose every run is in History.
- **Expected exposure, scheduled:** the services each device SHOULD expose are derived from its
  intent and role (management SSH only from the management prefix, SNMP only to the collector,
  no HTTP where intent configures none), and compared with a scan. A difference is a finding:
  the scan proves the ACLs work as configured, not merely that they are configured.
- **Unknown hosts:** addresses that answer in a managed prefix and that NetBox IPAM does not
  record, each a finding naming the prefix and the first and last time it answered.

**Limits, always:** only the NetBox prefixes Mercury manages; role-gated (E5); rate-limited;
every scan audited with who, what, when and the result. A scan never leaves those prefixes,
whatever a person types.

**Depends on:** C762 (the Toolbox), E5, NetBox IPAM populated, E18 (scan history), a scanner
on the NMAS host (nmap's licence, the operator's decision).
**Phase 8 hook:** "is anything listening on the branch that shouldn't be?" becomes the
expected-exposure comparison for those devices, the scope read back before it runs.

## 5. Traffic analysis to findings

**What it does.** Turns traffic into Needs attention rows a person can act on:
- **baselines** per device and interface, same-hour over 7 days;
- **behaviour rules**: a scan, beaconing (regular small connections to one destination),
  off-hours bulk upload, DNS tunnelling (long or high-entropy names, volume), a protocol on an
  unexpected port;
- an optional **Zeek or Suricata sensor** on a mirror port, its output into Loki beside syslog
  and traps;
- **threat-intelligence lists**, refreshed in a way that also works offline (a downloaded list
  can be carried in).

Each row carries its evidence and a "why it matters" line, and goes through C534's known-noise
classification and rate rules, so a known pattern is recorded once, not raised every time.
**Rules decide; AI explains and triages.** Mercury surfaces and adds the network context (which
device, which port, whose lease, which intent); forwarding to a SIEM is supported, never
replaced.

**Depends on:** C801's flow data, E18 (baselines are history), C534 (known noise), the sensor
host and mirror port (lab work), list licences, E5 (who sees what).
**Phase 8 hook:** the AI explains a row ("beaconing every 300 s to one address since 02:00:
here is the device, the lease and the first flow") and proposes a triage; a person decides.

## 6. Management-access profile per device

**What it does.** The ports Mercury reaches a device on (SSH, NETCONF, HTTPS/RESTCONF, SNMP)
become a profile, resolved device → role → site → default, as credentials already are, and
stored in a NetBox custom field (NetBox holds WHICH profile, as for credentials). Every
connection path reads it; a test refuses a hardcoded port 22 anywhere a device is reached
(today two remain: `modules/connection.py`'s reachability probe and the Reload's
`modules/nsot/reload_op.py`).

**Changing a port is lockout-proof**, as rotation is: hold the device, ADD the new port
alongside the old, prove a fresh login on the new port, and only then remove the old one; a
failed proof leaves the old port in place. On IOS the change is a **C764 pack** (`ip ssh port N
rotary G` with its `line vty` rotary group). The management path's repair route (CLAUDE.md:
a change to the path the tool reaches a device on needs a repair route independent of it) is
part of the pack's design.

**Depends on:** C764 (the pack), NetBox custom fields (the operator's data), the credential
resolution chain as its model, E18 (the change's record).
**Phase 8 hook:** "move r3's SSH to port 2222" becomes the pack's preview, every step named.

## 7. Common asks

Each is an Assure feature or report a network team asks for; ranked below by value against
effort. **The operator's priority picks are marked ★.**

| Rank | Ask | Value | Effort | What it builds on |
|---|---|---|---|---|
| 1 ★ | **Fleet-wide configuration search** over goldens (a line or a regular expression, every device, masked output, with the commit each match is in) | high: answered daily | low: goldens are committed and read through the masked path already | `repo.list_goldens`, `redact_text`, the C536 rule that a search matches raw and prints masked |
| 2 ★ | **Endpoint locator**: an address or MAC to the switch port, through ARP, then the MAC table, with history | high | medium: a reader of ARP and MAC tables (allowlisted reads) and their history | the reader framework, E18, Kea's leases |
| 3 ★ | **CVE and end-of-life matching**: each device's platform and version against Cisco's PSIRT openVuln API and EoX dates | high | medium: an outbound integration (an API key, the operator's) and a version inventory Mercury already reads | `platform_facts`, the integration pattern, `outbound` |
| 4 ★ | **Benchmark compliance packs** (DISA STIG and CIS for IOS and IOS-XE) as Assure verifiers, with an exportable report | high | high: each rule a verifier, many rules; the report reuses C799's export | Assure's verifier model (IBN_DESIGN section 2), C764, C799 |
| 5 | **"What changed" for a window**: commits, deploys, drift, acknowledgements, restarts, NetBox changes | high | low: the sources exist; History already joins several | History's timeline, C799's sources |
| 6 | **Capacity trending**: 95th percentile per interface, a forecast of when it crosses a threshold | medium | low: Prometheus holds the counters (90 days) | Prometheus, a forecast over its range query |
| 7 | **Availability reports** per device and site | medium | low to medium: link and reachability history | E18, `restarts`, reachability |
| 8 | **Expiry warnings**: certificates, licences, support contracts, as Needs attention rows | medium | medium: certificates are readable; contracts need a source (NetBox or a file) | Needs attention, C800's report card pattern |
| 9 | **Asset and finance report**: inventory with serials, models, ages, support status | low to medium | low once EoX (3) exists | NetBox, `device_serials`, 3 |

The four picks lead the ranking on value. Search and the "what changed" report are the
cheapest; STIG compliance is the largest and reuses most of the others.

**Depends on:** each row's last column; E5 for anything raw; E18 for every history.
**Phase 8 hook:** each is a question a person asks in words ("which devices still run
`transport input telnet`?", "where is 00:50:56:aa:bb:cc?", "which of our versions are
affected by this advisory?"), turned into the deterministic query and read back.
