# Flows: export configured and supervised by Mercury, stored elsewhere (a design)

**FUTURE, post-cutover: not Phase 7 work.** Sorted against docs/MERCURY_CHARTER.md (section "New
findings") as FUTURE on 2026-10-16: worth doing, not now. Nothing here is built; this is a
design note, with no code, NetBox, Grafana or device change behind it. It is one of the five
notes the operator asked for on 2026-10-16 (docs/SITES_DESIGN.md, docs/FLOWS_DESIGN.md,
docs/EDGE_ARCHITECTURE.md, docs/IPAM_IMPORT_DESIGN.md, docs/BRINGUP_FROM_DOCUMENTS.md), with a
sixth, docs/OFFLINE_OPERATION.md. The parts of the satellite case (the operator's item 7) that
concern flows are in section 6. Every module named below was read before the sentence about it
was written; where the code lacks a property, the sentence says so.

## 1. The decision, in five lines

1. Flow records never go into Prometheus. One series per address pair, port and protocol is
   unbounded cardinality. They go into a flow store (ClickHouse behind a collector) on its own
   VM, never the NMAS host.
2. Prometheus keeps only small aggregates, labelled by what the inventory already bounds
   (device, role, and site once docs/SITES_DESIGN.md lands), never by an address or a port.
3. Mercury configures flow export and supervises it. It stores no flows:
   - a `netflow` section in the monitoring profile;
   - the exporter configuration rendered by the platform templates and sent by the deploy
     pipeline (preview, confirm, verify, record);
   - the collector's expectations generated from the committed goldens, as
     `modules/prometheus_targets.py` generates Prometheus's targets;
   - a Needs attention row for an exporter the collector has not heard from;
   - a Top talkers link on the device page.
4. Grafana enriches flows with NetBox's facts (address to device, prefix and site) through the
   NetBox data source plugin, under a NetBox token of its own that is read-only and that
   Mercury never holds.
5. On an expensive or slow link (a satellite kit, a remote site), export is sampled, its volume
   is measured per site, and the raw flows stay on the near side of the link.

This fits the charter's table of owners: monitoring facts belong to Prometheus and Grafana,
and Mercury "reads; generates targets and rules from the inventory". The flow store becomes the
owner of flows, and Mercury generates its expectations and reads its answers in the same way.

## 2. What exists today

### 2.1 Mercury had a NetFlow collector, and it was removed on purpose

The in-process collector `modules/netflow_collector.py` (UDP 9996) was removed with the AI
family on 2026-10-14 (D15; docs/ARCHITECTURE.md, the module map's "Collectors and checks" and
its note that nothing listens on a UDP port now). Its settings key `collector_netflow_enabled`
is declared RETIRING in `modules/settings_scope.py` and read by nothing (docs/SETTINGS.md).
This design does not bring the collector back. Mercury stays a process that listens on no UDP
port, and a new setting never reuses the retiring key.

### 2.2 Targets generated from goldens: the pattern to copy

`modules/prometheus_targets.py` is the model for everything Mercury generates for a collector:
- `generate()` reads the inventory (`inventory()`) and each device's COMMITTED golden
  (`read_golden()`), and a device is a target only when its golden configures SNMP
  (`monitoring_coverage.configured()`). An unreadable golden RAISES rather than reading as "not
  configured", so the keeper records a failure and the files stay as they were.
- It refuses and names, never guesses: a device with no address, or an address two devices
  hold ("neither is scraped under it until one address is one device"), and it says when a
  device has no role.
- `render()` is deterministic and `_write_644()` atomic, so an unchanged inventory writes the
  same bytes.
- The keeper (`start_keeper()`, `_keeper_loop()`) regenerates on every sender:
  `inventory_changed()` from the inventory writers, `golden_hook()` on a commit that changed a
  golden, and a backstop every `KEEPER_BACKSTOP_SECONDS` (300 s). Every run is recorded in
  `data/prometheus_targets_sync.json`.
- `check()` and `compare()` read what the running Prometheus has LOADED and DISCOVERED, and
  say `ok`, `settling` (inside one scrape interval) or `differs`, naming both operands. This
  becomes a job-health row through `health_rows()` (wired in `modules/job_health.py`,
  `prometheus_target_rows()`).

### 2.3 The monitoring profile

`modules/nsot/profile.py` holds the network's profile at `PROFILE_REL`
(`profiles/monitoring.yml`), and `SECTIONS` lists the sections it knows: snmp, syslog, ntp,
management, lldp, cdp, telemetry, ip_sla. `problems()` refuses any other section name, so
`netflow` is not a section today. Each section applies by `platforms` and `roles`
(`applies()`); a device's intent may exclude it with a reason (`excluded()`); and `effective()`
is the one merge, with the device's own value winning. `ip_sla` is the precedent for a section
that holds a POLICY and no data: `problems()` refuses `data` under it, and
`modules/nsot/ip_sla_policy.py` turns the policy into operations committed into each device's
own intent (docs/MONITORING_PROFILE.md section 6).

`modules/nsot/profile_propose.py` derives each section from its connector (`DERIVED`: SNMP
needs `prometheus_url`, syslog needs `loki_url`), and proposes a section only where its
connector is configured. The management section reuses `syslog_source_interface` as the
interface management protocols leave from, so the network declares it once.

### 2.4 Coverage and the not-reporting reader

`modules/monitoring_coverage.py` decides from each committed golden what a device is
configured for (`CHECKS`: SNMP, syslog, the heartbeat, telemetry), and which integrations the
network uses (`expected()`, `_expected_columns()`). Its `rows()` are job-health rows in the
`not_monitored` state. `COLUMNS` are Monitoring › Coverage's columns.
`modules/readers/coverage_reporting.py` records when each source last ARRIVED, with ONE query
per source for the whole fleet (Prometheus's targets, telemetry by `source`, Loki for syslog and
the heartbeat), and `judge()` turns an arrival into `not_reporting` for a configured cell. It
stores arrivals only, never a verdict. Flows fit beside these as one more source and one more
column.

### 2.5 The exporter configuration has no model yet

The IOS-XE parser (`modules/nsot/parsers/cisco_iosxe.py`) has handlers for telemetry
subscriptions and NETCONF, and none for `flow record`, `flow exporter`, `flow monitor`,
`sampler` or an interface's `ip flow monitor`. Per `modules/nsot/parsers/base.py`, a block with
no handler goes into `unmodeled` verbatim, with its section context, so a device configured for
flows by hand today round-trips but cannot inherit anything from a profile. The template
(`modules/nsot/templates/cisco_iosxe/base.j2`) renders telemetry from `vars.telemetry`, and
has nothing for flows.

### 2.6 Verify's scope

`modules/nsot/verify_scope.py` makes verify QUICK only when every top-level section a program
sends is in `MANAGEMENT` (terminal lines, logging, SNMP, NTP, banners, users, management
sources); anything else is FULL, including BGP's hold-time watch. "A family joins MANAGEMENT
by a decision written here, never by resemblance." So a flow program is FULL today.

### 2.7 Needs attention

`modules/attention.py`: `row()` is the only constructor. It refuses a kind not declared in
`ROW_KINDS` (what is wrong and the action), and it reads `CLEARS` for how the row clears. A
source is one `source_result()`, and an unreadable source is a row of its own, never an
absence. `SOURCES` lists the sources and `SOURCE_KEYS` the data keys that re-read each. Rows
about one cause fold by `attach_to` (`_fold_one_cause()`, `_fold_known_unmonitored()`).
`modules/nsot/blast_radius.py` is Reload's gate 6: from committed intent, it works out what
else Mercury loses reach to while one device is down.

### 2.8 The device page and Grafana

`modules/device_page.py` builds the Monitoring tab (`monitoring()`) from the network's device
dashboard role (`device_dashboard_settings()`), and `streams_telemetry()` decides from the
committed configuration, never from whether series exist, whether a device streams. The tab
is signed off (`tests/signed_off_screens.py`, `tab:monitoring`). `modules/panels.py` draws
native panel types only (`NATIVE_TYPES`) and links the rest out (`drawn_elsewhere()`). Its
`check_range()` knows two backends' limits (`LIMITS`: Prometheus 90 days, Loki 30 days 1 hour),
and a backend it does not know passes unchecked. `modules/integrations/grafana.py` is
read-only (`query()` through `api/ds/query`, `test_connection()`).
`modules/readers/grafana_dashboards.py` reads Grafana's dashboards and data sources (`api/search`,
`api/frontend/settings`, `api/datasources`). The device dashboard is built by
`deploy/grafana/build_nmas_device.py`, imported by the operator: "The NMAS never pushes a
dashboard."

### 2.9 NetBox tokens

`modules/netbox_client.py` keeps one token, `netbox_token`, encrypted at rest
(`get_netbox_config()` decrypts it), behind the fail-closed write gate (`allow_writes`).
`READ_PROBES` lists the types Mercury reads, and docs/SERVICE_ACCOUNTS.md (Part 1, section 1.3)
gives the account `nmas` view, add, change and delete permissions. That token is not suitable
for Grafana: it can write.

## 3. Where flows live

### 3.1 Never in Prometheus

Prometheus keeps one series for each distinct label set. Flow keys (source and destination
address, ports, protocol, interface) multiply without a bound the inventory controls, and
`modules/prometheus_targets.py` works so that every label it adds (device, role) is bounded by
the inventory. Flow records therefore go to a store built for them. Prometheus receives only
aggregates whose labels come from a fixed set: `device`, `role`, `site` (docs/SITES_DESIGN.md),
`network`, and the collector's own `exporter` address. Never `src`, `dst`, a port or an ASN. A
test holds every aggregate rule to that set (see "Tests it needs").

### 3.2 The flow store and its collector

ClickHouse holds the records, on a VM of its own (creating that VM is a Proxmox write, so it is
the operator's), because a flow store's disk and memory use grows with traffic, and the NMAS
host's must not. The collector in front of it is chosen by measurement (section "Measurements
still owed", M6), from:

| Candidate | What it is, as far as this design depends on it | To measure before choosing |
|---|---|---|
| Akvorado | A flow pipeline with its own console, storing in ClickHouse | ingest from the lab's IOS-XE exporter; the per-exporter "last heard" query; its resource use on the flow VM; its licence |
| goflow2 | A decoder (NetFlow v9, IPFIX, sFlow) that emits records for a sink | the sink into ClickHouse; the metrics it exposes per exporter, and their labels |
| pmacct | A collector suite (nfacctd) with many back ends | the same, and the effort of its configuration |
| Orb | NetBox Labs' agent | **its self-hosted path is measured first**: whether it runs with no cloud service, and what it collects |

Each candidate's licence is read from its own source at evaluation, and adopting it is the
operator's decision (CLAUDE.md's Phase 7 stops: a new third-party licence). None of them is
shipped in this repository, so none enters docs/THIRD_PARTY.json unless that changes.

### 3.3 What Prometheus keeps

The aggregates, scraped from the collector's own metrics where it exposes them, or recorded by
a query against the flow store on a schedule (whichever M6 shows the chosen collector
supports):
- records and bytes received per exporter per second, and records the collector dropped;
- export bytes per second per site (the satellite case, section 6.2);
- the time each exporter was last heard.

The detail stays in ClickHouse, behind the collector's console or Grafana.

## 4. Mercury configures and supervises; it stores nothing

### 4.1 The `netflow` section of the monitoring profile

A ninth entry in `SECTIONS`, with two parts:

```yaml
netflow:
  source: flows                    # the connector: the collector named in Settings
  platforms: [cisco_iosxe]         # until another platform is measured able to export (M1)
  data:
    netflow:
      exporter: {name: NMAS-EXPORT, destination: "<collector>", port: "<port>",
                 vrf: "",            # set where the collector is reached through a VRF
                 template_timeout: 60}
      record: {name: NMAS-RECORD, match: [...], collect: [...]}
      monitor: {name: NMAS-MONITOR, active_timeout: 60, inactive_timeout: 15}
      sampler: {name: NMAS-SAMPLER, one_out_of: 100}   # absent: every packet
  attach: upstream                 # a POLICY: which interfaces, never interface names
```

- **The data** is in the parsers' host_vars shape, as every other section's is. It is merged
  by `effective()`, and the device wins where it holds a value. The exporter's source interface
  is not in the section. It is `syslog_source_interface`, the interface management protocols
  already leave from (the management section's rule in `modules/nsot/profile_propose.py`), so
  the network declares it once.
- **The attachment** is a policy, as `ip_sla`'s is, because interface names are the device's
  own data. The values are `upstream` (the interfaces facing what the device depends on,
  computed as `ip_sla_policy`'s `upstream`), `routed` (every routed interface except the
  management interface), and `none`. A preview suggests each device's interfaces, the person
  accepts or edits them, and they are committed into the DEVICE's intent; then a scoped deploy
  sends them. This is the IP SLA add path, reused (docs/MONITORING_PROFILE.md section 6).
- **The values in the example are placeholders, not recommendations.** The timeouts and the
  sampling rate come from measurement (M2 to M5). `template_timeout` is set EXPLICITLY, for a
  reason section 4.4 gives.
- **The connector.** `DERIVED` gains `"netflow": ("flows", "flow_collector")`, so the section is
  proposed only where a collector is named. `flow_collector` is a new setting in the
  `host:port` shape `telemetry_receiver` already uses (`modules/settings_schema.py`), empty by
  default (no section proposed, so prior behaviour is reproduced). Why a setting and not a
  measurement: nothing Mercury holds can say where the network's collector is.
  `modules/integrations/monitoring_profile.py` gains a Test for it that says, as it says of
  syslog, that one-way UDP cannot be tested by sending, and that reads the collector's own API
  instead (section 4.6).
- **Coverage** gains a column, `("netflow", "Flows")`, and `CHECKS` gains the shape of a
  configured exporter: a `flow exporter` block whose destination is the network's collector,
  and at least one interface with a monitor attached. A device configured for one without the
  other is said as exactly that.

### 4.2 The exporter configuration, from templates and verified by deploys

- **Model first.** The IOS-XE parser gains handlers for `flow record`, `flow exporter`,
  `flow monitor`, `sampler`, and an interface's `ip flow monitor <name> [sampler <name>]
  input|output`. The template gains a macro that renders them. The round trip is proven on a
  real capture from the lab's IOS-XE device (M1), never on typed text. The IOS (vIOS) parser
  gains them only if M1 shows the platform has them.
- **Sent by the pipeline, merge-only.** Applying the section is `profile_apply`'s scoped
  deploy: each device's exact program is previewed, confirmed by hash, applied with the device
  held, verified, rolled back on failure and recorded. Nothing about flows bypasses
  `modules/pipeline.py`.
- **Verify's scope is a decision for the operator, written in `verify_scope.py` if taken.** The
  four global sections (`flow record`, `flow exporter`, `flow monitor`, `sampler`) describe
  what a device reports, not what it forwards, and could join `MANAGEMENT` as a "flow export"
  family. The interface lines stay FULL in any case: they are interface sections, and
  attaching a monitor costs the data path something M3 measures. Until the decision, every
  flow program is FULL, which is slower and never unsafe.
- **Removal is Mode B.** Taking a monitor off an interface is a removal shape measured with
  `scripts/nmas-removal-probe` and recorded in `modules/nsot/removal_measured.json` (M8) before
  Mode B offers it. Until then it is refused, as every unmeasured shape is.

### 4.3 The collector's expectations, generated from goldens

A new module, `modules/flow_exporters.py`, is `prometheus_targets` for the flow collector:
- **The population is a property, not a proxy:** a device is an expected exporter when its
  COMMITTED golden holds a `flow exporter` whose destination is this network's collector AND an
  interface with that exporter's monitor attached. Inventory membership alone is not enough,
  and neither is a profile that says it should export.
- **The exporter address is derived, never assumed to be the management address.** It is the
  address of the exporter's `source` interface in the device's intent. `prometheus_targets`
  keys on the inventory's `ip`, which is the address Mercury manages the device on, and a
  collector sees the export packet's source instead. A `flow exporter` with no `source` line
  exports from its egress interface, which intent cannot name with certainty. Such a device is
  NAMED as "its exporter has no source interface, so the address the collector will see is not
  known", never guessed.
- **The same refusals:** an address two exporters would use is refused for both, named.
  Identical kits and repeated site addressing are where this happens: within one instance, a
  site's VRF disambiguates (docs/SITES_DESIGN.md), and the expectation carries `(site,
  address)` and the exporter's observation domain where M6 shows the collector records it.
- **Written as Prometheus's files are:** a deterministic render, atomic writes, the same three
  senders (`inventory_changed()`, `golden_hook()`, the backstop), the same keeper record. The
  file is Mercury's expectation. A rendered fragment of it can also be the collector host's
  source allowlist, which docs/NSOT_STAGE10_PLAN.md (section 4.2, "SNMP traps and NetFlow
  accepted from anyone") asks for. Installing that fragment is the operator's one-time step,
  as for the targets (docs/PROMETHEUS_TARGETS.md, "The one-time install").

### 4.4 The Needs attention row: an exporter the collector has not heard from

- **The read.** `modules/readers/coverage_reporting.py` gains a fifth source: ONE query per
  collector for the whole fleet, returning each exporter address and when it was last heard.
  The query's form depends on the collector chosen (M6). A read that returns exactly its page
  size is refused as truncated. Like the other sources, it stores arrivals and no verdict.
- **The judgement.** `judge()` gains a `netflow` rule: silent when the last arrival is older
  than about 2.5 times the measured interval between an exporter's packets. That interval is
  bounded because `template_timeout` is set explicitly. An exporter on an idle interface
  sends no data records, but it still sends its templates, so silence means something only if
  the collector counts a template-only packet as heard (M5). If it does not, the judgement is
  "not judged while the device forwards nothing", and never "silent".
- **The source.** A new `flows_source` in `SOURCES`, with two kinds declared in `ROW_KINDS`
  and `CLEARS`:
  - `("flows", "silent")`: "a device configured to export flows has not been heard by the
    collector for <age>". Action: "check the device answers and its exporter's destination
    and VRF on its Monitoring tab, then read its last export". It clears when the collector
    hears it again (`resolves`).
  - `("flows", "stranger")`: "the collector hears an exporter no device's configuration names".
    Action: "find the device sending from <address>, or add it to the network". It clears when
    the expectations name the address or the collector stops hearing it (`resolves`).
  `SOURCE_KEYS["flows_source"] = ("flows", "goldens")`. A collector that cannot be read is the
  source's `unreadable` row, never "every exporter silent".
- **One cause, one row.** A silent exporter on a device the reachability reader holds
  unreachable attaches to that device's row (`attach_to`). An exporter cut off from the
  collector because ANOTHER device is down (`blast_radius.radius()` names it) attaches to that
  device's row, and the row names the exporters it hides. That is Reload's gate-6 reasoning
  applied to the path from the exporter to the collector.
- **A deploy that just sent the exporter** is `settling` until one window after its receipt,
  dated, with when to look again, never silent at once (the `settling` state of
  `prometheus_targets.compare()`).

### 4.5 Top talkers from the device page

- **A link, not a native panel, first.** The Monitoring tab gains "Top talkers" for a device
  that is an expected exporter. It opens the network's flows dashboard in Grafana, filtered to
  the device. A device that does not export gets the words, decided from its committed
  configuration as `streams_telemetry()` decides telemetry ("r2 doesn't export flows: its
  configuration has no flow exporter"), never from whether records exist right now.
- **The dashboard** is built by a builder in `deploy/grafana/` beside
  `build_nmas_device.py`, under the same rules: no job or data source named by its literal
  value, a `device` variable, and a `noValue` sentence on every panel. The operator imports
  it. Its UID is a third dashboard role, `grafana_flows_dashboard_uid`, empty by default (the
  page says so), because a UID cannot be measured, the same reason the FLEET and DEVICE roles
  are settings. CLAUDE.md's table of roles gains a row, which the operator pastes.
- **Drawing it natively comes later, and only after one change:** `panels.check_range()`
  passes a backend it does not know with no limit. A flow panel drawn over a range longer
  than the flow store keeps would therefore read as the whole range. `LIMITS` gains the flow
  store's retention, measured, before any flow panel is drawn on the tab.
- **The tab is signed off, so the link needs a board** (CLAUDE.md: no new control without a
  mockup and sign-off) and the board-fidelity comparison afterwards.

### 4.6 Settings and the integration

- `flow_collector` (section 4.1), and `flow_collector_api`: the collector's read API (the
  ClickHouse HTTP interface or the collector's own), which the reader asks. Both belong to an
  integration group (`modules/integration_groups.py`), so a network inherits Default's
  collector or names its own, and a reader serving every list reads each distinct collector
  once.
- A `FlowsIntegration(IntegrationClient)` in `modules/integrations/`, read-only, whose
  `test_connection()` asks an endpoint that needs its credential, as Grafana's asks `api/user`
  (C354), so a refused credential is never "reachable".
- Its credential, if the API needs one, is a secret in the secrets store, masked on the way
  out, and never returned.

## 5. Enrichment: the NetBox data source in Grafana

- **Adopted here:** the `netboxlabs-netbox-datasource` plugin, 1.0.x. The operator read on
  2026-10-16 that Grafana 13.2.0 and NetBox 4.6.9 meet its requirements; the install re-reads
  the plugin's published requirements against the versions then running. It joins a flow's
  addresses to NetBox's IP addresses, prefixes, VRFs, sites and devices in Grafana, at query
  time.
- **Its own NetBox account and token, read-only.** A NetBox user for Grafana alone, with VIEW
  on only the types its panels read: IPAM IP address, prefix and VRF, and DCIM site, device
  and interface. That is a subset of `nmas-view` (docs/SERVICE_ACCOUNTS.md section 1.3) with
  none of `nmas-add`, `nmas-change` or `nmas-delete`. The token is held in Grafana's data
  source configuration and never in Mercury. It is never `netbox_token`, and Mercury never
  reads, stores or prints it. A Grafana that can only read NetBox cannot become a second
  writer to it, which the write gate and docs/MERCURY_CHARTER.md's table of owners both
  require.
- **What Mercury can check without the token.** `modules/readers/grafana_dashboards.py`
  already reads Grafana's data sources, so "the flows dashboard uses a NetBox data source, and
  Grafana holds none" is a state Mercury can draw. Whether Mercury can see that token's
  expiry is M7: the `nmas` account's view on `users/tokens/` was added so it could read its OWN
  token's expiry. If NetBox lists other users' tokens to it too, no setting is needed (a
  measured default before a setting); if not, the expiry is declared beside
  `grafana_token_expires` and its kind (`attention.DECLARED_EXPIRY`).
- **Containment, measured before relying on it.** An exact address joins to an IP address
  object. "This address lies in that prefix" is a containment test, not an equality join, so
  whether the plugin answers it in a panel without one NetBox query per row is M7. If it
  cannot, prefix and site enrichment moves to ingest time: Mercury generates a prefix table
  (prefix, VRF, site, role) from what it already reads from NetBox, with `prometheus_targets`'
  generator, keeper and check, and the collector loads it where M6 shows it accepts one. The
  plugin then keeps the device names.

## 6. Satellite and expensive links (item 7's flow parts)

The operator's decision of 2026-10-16 makes each fly-away kit its own network on its own
Mercury instance, under a headquarters manager (docs/EDGE_ARCHITECTURE.md). For flows, that
means two cases.

### 6.1 Sampled export

- On a kit, or a site behind a costly link, the profile's `sampler` is set, and headquarters
  chooses the rate in the build standard's profile: a hard decision made in advance, never by
  the kit operator.
- The collector must scale sampled counts back up. Whether the C8000v exports its sampling
  rate in an options template, and whether the chosen collector applies it, is M4. A sampled
  count drawn as if unsampled is a wrong number that looks right, so until M4 the flows
  dashboard says "sampled 1 in N" on every panel.
- Sampling also lowers the exporter's CPU, which matters on a small kit router; M3 measures
  it.

### 6.2 Per-site flow volume

- **Where the records go.** On a kit, the collector runs on the kit, on hardware sized for it
  (M11, with docs/EDGE_ARCHITECTURE.md). Raw flows never cross the satellite. Headquarters
  pulls bounded summaries on demand (top N talkers for a window), which is the edge design's
  rule for bulky data. Within one instance managing several sites
  (docs/SITES_DESIGN.md), a remote site's export to a central collector crosses the WAN, and
  sampling bounds it.
- **What is measured.** Export bytes per second per site is a Prometheus aggregate labelled
  `site`. The profile's preview estimates it before anything is sent: records per second at
  the site (measured), times bytes per exported record (measured, M2), divided by the sampling
  rate. It states the estimate with its basis, and says "not measured" where a number is not.
- **A budget headquarters sets.** A site's flow budget (in bytes per second) is part of the
  build standard. A profile whose estimate exceeds it is refused at preview, naming the
  estimate, the budget and their operands.

### 6.3 Silence behind a dead uplink

When a kit's or site's uplink is down, every exporter behind it goes silent at once. Those
rows attach to the one "site unreachable" row (docs/SITES_DESIGN.md; docs/EDGE_ARCHITECTURE.md
for the kit fleet) by the attach rule in section 4.4, never as N rows. On a kit, the local
collector still hears its own exporters while the uplink is down, so the kit's own Needs
attention stays truthful, and headquarters shows the kit's last-known state with its age.

### 6.4 Time limits from measured loss, not one global number

Export is one-way UDP, so round-trip time does not slow it, and loss is what matters. NetFlow
v9 and IPFIX send templates separately from data. If a template packet is lost, the collector
cannot decode data from that exporter until the next template arrives, so the template
timeout bounds the gap. On a lossy satellite link, the build standard sets a shorter template
timeout, chosen from the link's measured loss (the upstream-manager test in
docs/EDGE_ARCHITECTURE.md). The "silent" window of section 4.4 is derived per site from that
timeout, about 2.5 times the measured interval between packets, never one global number. The
decoding gap against the template timeout is M10.

## 7. In the lab (examples only; the product names none of this)

From lab/REDEPLOY.md and the register's records. The lab's own files hold the rest, and none of
it enters the product (tests/test_lab_specifics.py):
- **Routers:** r1 to r4 and r6 are C8000v (IOS-XE), the candidates to export. r5 is in the lab
  and not in Mercury. r2 is the IOS-XE device for staged runs.
- **Switches:** s1 to s4 are vIOS-L2 (IOS 15.2), likely unable to export flows (M1 decides).
  Staged runs and probes never run on s3, which is CPU-starved and carries the fleet's
  management path. s1 is the IOS device for staged runs.
- **Hosts:** h1 to h4 and web. h1 and h2 reach the routers through s1, and h3 and h4 through
  s2 (measured 2026-10-06, the register's C534). web's attachment is read from the lab's
  topology when the measurement is planned.
- **Throughput cap:** every lab C8000v forwards at most about 10 Mbit/s (the unregistered
  default, measured 2026-10-09; docs/NSOT_DRAINED_DESIGN.md section 10). A traffic generator's
  load stays well under that, or the flows measure the licence's shaper.
- **The management VRF:** the lab's routers reach their management network through a VRF, so
  the exporter's `vrf` field is exercised there.

## 8. Where a wrong thing could look right, and what makes it visible

| Feature | Wrong, yet looks right | Made visible by |
|---|---|---|
| Expectations | the collector hears the device under an address other than its management one, and the device reads as silent | the exporter address derived from the `source` interface (4.3), and the `stranger` row naming the address actually heard |
| Silent row | an idle interface sends no records, and the device reads as silent | an explicit template timeout, and M5 deciding whether a template counts as heard (4.4) |
| Top talkers | a range longer than the flow store keeps reads as the whole range | `LIMITS` gains the store's retention before native drawing (4.5) |
| Sampling | sampled counts drawn as totals | "sampled 1 in N" on every panel until M4 proves the scaling (6.1) |
| Enrichment | a stale prefix table names the wrong site | the table's age drawn beside it, and its keeper's record read as a job-health row, as the targets' is |
| Collector down | an unreadable collector looks like every exporter silent | the source's own `unreadable` row (4.4) |

## What it touches

- `modules/nsot/profile.py` (`SECTIONS`, `problems()` for the `attach` policy),
  `modules/nsot/profile_propose.py` (`DERIVED`), `modules/nsot/profile_apply.py` (the scoped
  apply), and `modules/nsot/ip_sla_policy.py`'s suggestion pattern reused for the attachment.
- `modules/nsot/parsers/cisco_iosxe.py` (new handlers), `modules/nsot/templates/_common.j2` and
  `modules/nsot/templates/cisco_iosxe/base.j2` (a flow macro), and `cisco_ios` only if M1 shows
  vIOS exports.
- `modules/nsot/verify_scope.py` (only if the operator decides on a "flow export" family).
- `modules/nsot/removal_measured.json` (the measured removal shapes).
- New: `modules/flow_exporters.py` (generate, render, write, keeper, check),
  `modules/integrations/flows.py`, a builder in `deploy/grafana/` for the flows dashboard.
- `modules/monitoring_coverage.py` (`CHECKS`, `COLUMNS`, `_expected_columns()`),
  `modules/readers/coverage_reporting.py` (the fifth source and its `judge()` rule).
- `modules/attention.py` (`flows_source`, `ROW_KINDS`, `CLEARS`, `SOURCES`, `SOURCE_KEYS`),
  `modules/invalidation.py` (the `flows` key), and `modules/job_health.py` (the keeper's row).
- `modules/device_page.py` (the Top talkers link's state), `templates/v2/` (the Monitoring
  tab's link, after its board), `modules/panels.py` (`LIMITS`, later).
- `modules/settings_schema.py`, `modules/settings_scope.py`, `modules/integration_groups.py`,
  docs/SETTINGS.md (the new settings); `modules/integrations/monitoring_profile.py` (the Test).
- Off the NMAS host: the flow VM (the operator's to create), the collector, ClickHouse, the
  Grafana plugin and its NetBox account.
- The manual (`docs/manual/`): a page for flows and a How it works page for applying the
  section; docs/MONITORING_PROFILE.md and docs/PROMETHEUS_TARGETS.md gain the flow parts.

## Tests it needs

- **Profile:** `problems()` accepts `netflow` with data and an `attach` policy, refuses an
  unknown policy, and refuses a `netflow` section with no data; `effective()` merges it with the
  device winning; existing version-1 documents read unchanged.
- **Round trip:** a real IOS-XE capture holding every flow block parses into the model and
  renders back byte for byte, and no flow line is left in `unmodeled` (fixtures are captures,
  minimally edited).
- **Expectations:** a device with an exporter and no attached monitor is not expected; the
  exporter address comes from the `source` interface; a missing `source` is named; a shared
  address is refused for both devices; an unreadable golden raises; the render is
  deterministic. A floor on the population, and a planted case that the check finds.
- **Judgement:** silent, heard, settling, not judged (idle), and unreadable, each with both
  operands named. Each is shown able to fail by removing the property it guards.
- **Needs attention:** both kinds declared with their action and how they clear
  (tests/test_attention_rows_act.py, tests/test_acknowledge.py); an attachment to the
  reachability row and to the blast-radius device's row; `SOURCE_KEYS` held to `SOURCES`.
- **Reader:** one query per collector for the fleet (tests/test_scale.py's rule); a full page
  is refused as truncated; no live collector touched (the network guard).
- **Cardinality:** every Prometheus aggregate rule the design ships uses only `device`, `role`,
  `site`, `network` and `exporter` as labels.
- **Device page:** the link's states (exports, does not, unreadable) decided from the
  committed configuration; the fixed-read test in tests/test_devices_v2.py still holds; the
  board-fidelity record for the Monitoring tab; the manual's pages (tests/test_manual.py).
- **Settings:** the new keys are declared with defaults that reproduce today's behaviour
  (tests/test_settings_write_path.py); the collector credential is never returned
  (tests/test_no_get_returns_a_stored_secret.py).
- **The dashboard builder:** its own `--check` test, as tests/test_nmas_device_dashboard.py
  holds the device dashboard's builder.
- **Lab specifics:** nothing lab-named in the product (tests/test_lab_specifics.py).

## What it must not break

- **Prometheus's targets.** `modules/prometheus_targets.py`'s files keep their bytes. The flow
  expectations are a separate file with a separate check, and no flow label reaches an SNMP
  target group.
- **The NMAS host listens on no UDP port.** No collector runs in Mercury's process or on its
  host.
- **The retiring `collector_netflow_enabled`** stays retiring and unread, and no new key reuses
  it.
- **The profile's existing sections, merge and serialisation** (`dump()`), and every committed
  profile document.
- **The deploy lifecycle:** preview, confirm by hash, merge-only, verify, rollback and record,
  with no flow line sent any other way. Verify stays FULL for flow programs until the operator
  decides otherwise.
- **The device dashboard and the FLEET and DEVICE roles,** unchanged. The flows dashboard is a
  third role.
- **Mercury's NetBox token and its permissions.** The plugin's account is separate, and NetBox's
  write gate is untouched.
- **Scale:** no per-device work per request; the collector is asked once per read for the
  whole fleet.
- **Coverage's existing columns and rows** (`monitoring_coverage.rows()`), and Needs
  attention's existing kinds.

## Measurements still owed

None is taken now. All of them avoid 08:30 to 09:10 UTC (the nightly backup) and s3. A device
change is a Mercury operation with preview and record; a read goes through Mercury's read-only
paths.

| # | Question | Method | Where |
|---|---|---|---|
| M1 | Which lab devices can export: C8000v Flexible NetFlow and IPFIX; vIOS-L2, likely not | reads first (`show flow exporter`, `show flow monitor`, `show sampler`) through Mercury's Show commands on r2 and s1, recorded in History (`show` is an allowlisted verb in `modules/readonly_commands.py`; each command's tier there is read first); then a staged apply of a minimal exporter to r2 through the pipeline, and to s1 only if its reads show the commands | via Mercury, on r2 and s1 |
| M2 | Bytes per exported record and records per export packet, at a known load | the collector's own counters on the flow VM, during M9's bounded run | the flow VM, the lab |
| M3 | The CPU cost of a monitor attached to one interface, unsampled and sampled | Prometheus's CPU series for r2 before and during M9's run, at a fixed rate well under 10 Mbit/s | read from Prometheus on the NMAS host |
| M4 | Whether the C8000v's sampler (random 1 out of N) works, and whether the sampling rate is exported and applied by the collector | a sampled monitor on r2; counts at the collector against the interface counters | r2 via Mercury; the flow VM |
| M5 | Whether the collector counts a template-only packet as heard, and the interval between packets at a set template timeout with no traffic | an idle exporter on r2, the collector's last-heard read over three template periods | the flow VM |
| M6 | The collector candidates: ingest from r2, per-exporter last-heard query, exposed metrics and their labels, resource use, licence; Orb's self-hosted path first | each installed in turn on the flow VM, fed by r2 | the flow VM (created by the operator on Proxmox) |
| M7 | Whether the NetBox plugin answers containment in a panel, and whether the `nmas` account's view on `users/tokens/` lists another user's token expiry | one panel against the plugin; one read-only `users/tokens/` read with Mercury's token, counting rows, printing no value | Grafana; NetBox, read-only |
| M8 | The removal shapes for an interface's `ip flow monitor` lines and the global flow sections | `scripts/nmas-removal-probe` on r2, recorded in `modules/nsot/removal_measured.json` | r2 |
| M9 | A traffic generator: whether iperf3 is in the h1 to h4 and web images; a bounded run (fixed duration, a rate well under the 10 Mbit/s cap) between the hosts and web; its stop confirmed by interface counters | in the lab's repository (`configs/host-net.sh` beside the topology), then a run with a set duration, stopped by its process identity, the stop read from Prometheus's interface rates (C534: a `docker exec` process outlived its tmux) | the lab host, by the lab's tooling, never the product |
| M10 | The decoding gap after a lost template, against the template timeout, under emulated loss | loss emulated on one lab link to the flow VM; gaps read at the collector | the lab host and the flow VM |
| M11 | A kit's hardware for a local collector and store | the chosen collector's resource use from M6, scaled to a kit's measured flow rate | with docs/EDGE_ARCHITECTURE.md's kit sizing |

## Dependencies on the other four notes

- **docs/SITES_DESIGN.md comes first.** It provides the `site` label beside `device` and `role`
  in `modules/prometheus_targets.py`, which the flow aggregates and the per-site volume carry,
  and the VRF per site that disambiguates repeated addressing in the expectations (4.3). It
  also provides the one "site unreachable" row that silent exporters attach to (6.3).
- **docs/EDGE_ARCHITECTURE.md reuses this note.** Flows are bulky data, pulled on demand and
  bounded across the link. A kit runs its own collector, sized with M11. The build standard
  carries the `netflow` section, the sampling rate and the flow budget. The upstream-manager
  test's measured loss sets the template timeout (6.4). A classified network's flows never
  leave its enclave, because flow records are values from that network.
- **docs/IPAM_IMPORT_DESIGN.md** puts the prefixes, VRFs and sites into NetBox that enrichment
  reads (section 5). Enrichment is only as good as that import, and before it a prefix NetBox
  lacks is drawn as "not in NetBox", never as a guess.
- **docs/BRINGUP_FROM_DOCUMENTS.md:** no direct dependency. A later bring-up step can add "the
  local collector hears this kit's router" as one more real read with a PASS line, once
  section 4.4 exists.
- **docs/OFFLINE_OPERATION.md (the sixth note):** the collector, ClickHouse and the Grafana
  plugin are installed from an internal mirror or a carried bundle on an installation without
  the internet.
