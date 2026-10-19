# The completion inventory: everything between Phase 7's close and Core 1.0

**Written 2026-10-19 (UTC), for the operator's triage** (the operator, 2026-10-18: "the path after
Phase 7", part 2). This is new: no earlier inventory existed to reconcile. **The triage and Core
1.0's sign-off are the operator's** (CLAUDE.md, the operating mode). Every home, size and
list below is a PROPOSAL. Documents only: no feature code until the operator signs off the
triage.

## How it was made

- **Status is MEASURED from the code at f15f6fbd,** never taken from a document's claim or from
  the operator's list. Each item names the file, function or route read. The scale:
  - **built**: the capability works as asked;
  - **partial**: some of it works, and what is missing is named;
  - **designed only**: a design document exists, with no code;
  - **not started**: neither.
- **Three read-only surveys** read the code:
  1. the register's open rows;
  2. the design documents and plans;
  3. the operator's cross-check list, with ZTP.
  Their key claims were re-read at their lines before use:
  - Lab 9 "not demonstrated within P.6" (NSOT_WRITEUP.md);
  - the ZTP responder reading only Default's fragment (`ztp_responder._fragment_entries`);
  - the Werkzeug server (`app.py:630`);
  - the records database holding receipts only (`records_db.STORES`);
  - Drained switched off (`drained.ENABLED = False`).
- **Sources:**
  - docs/OPEN_FINDINGS.md: every open A, B and UNKNOWN row as its own row, and the C rows by
    theme;
  - every design document in docs/ whose build has not happened;
  - NSOT_PLAN.md's remaining stages and P-items;
  - NSOT_STAGE10_PLAN.md;
  - PHASE8_PLAN.md;
  - the operator's cross-check list.
- **Homes:**
  - **Core 1.0**: in the program before any AI;
  - **Phase 8**: the AI;
  - **Stage 10**: the public release;
  - **post-1.0**: after Core 1.0, unscheduled.
  - Under the operator's definition, **Core 1.0 = a signed-off capability list plus no open A
    or B.** So every open A and B is Core 1.0 unless the operator re-ranks it. Where a row seems
    to belong elsewhere, it says "Core 1.0, or re-rank" and why. C rows are not A or B, so they
    may stay open at Core 1.0's finish. They are post-1.0 unless a Core 1.0 capability names them.
- **Sizes** are ESTIMATES, from comparable finished work, timed from commit times:
  - **S, under 2 h:**
    - C1316, the heartbeat check's rate-or-jitter verdict with its host measurement, about 1 h;
    - C1317, no-change windows as a setting, about 1.5 h with one refused gate;
    - C1192, Needs attention's record, about 2 h with a host measurement and one refused gate.
  - **M, 2 to 8 h:** one v2 screen part with its tests and manual, such as C1303 (History's Kind
    filter) or C1304 (Devices' select-all).
  - **L, over 8 h:** a capability with a board, a screen, an operation and its walk, such as
    DHCP on v2 (C529), Topology (P.11) or the v1 removal (P7-27). Each of those took days.
  - Phase 7's burn-down sized its items in agent-days and closed in 3.3 days of wall time
    (NSOT_WRITEUP.md, Phase 7's entry). So these sizes are hours of work, not calendar time.
- **Lab** names the CSCI 5840 lab an item serves: 8, 9 or 10. The handouts are still locked, so
  the mapping comes from NSOT_PLAN.md ("Labs 8 and 9, ZTP: P.6"; Lab 10's troubleshooting set)
  and LAB_REQUIREMENTS.md section 3.1c, and is provisional until a handout is mapped.
- **Minimum** says whether the item fits the charter's Minimum tier: 4 vCPU, 8 GiB, about 100
  GB. The whole stack, records database included, used about 4.3 GiB on the lab host on
  2026-10-14 (PHASE8_PLAN 10.8), so most items fit. Where an item adds a service whose
  footprint is unmeasured, it says "unmeasured".

## 1. Summary

**Counts by proposed home and size,** counted by a script over this document's own tables:
- each of section 2's 66 capabilities;
- section 3's 24 A and B rows and 50 UNKNOWN rows;
- section 4's themes, one item each, with T2 counted in section 2 instead.

160 items in all. An A or B row folded into a capability is counted in both places, so the
Core 1.0 count overstates its distinct work. Section 6's time box counts each piece of work once.

| Home | S | M | L | All |
|---|---|---|---|---|
| Core 1.0 | 14 | 28 | 19 | 61 |
| Phase 8 | 0 | 0 | 3 | 3 |
| Stage 10 | 0 | 3 | 18 | 21 |
| post-1.0 | 44 | 9 | 21 | 74 |
| done (K26, select-all) | | | | 1 |

**The proposed Core 1.0:** section 6, with its order and time box. **ZTP against P6_ZTP's
criteria for Labs 8 and 9:** section 5. **E18:** PHASE8_PLAN.md section 13.2 reports whether
feature 1 needs it. **What could not be placed:** section 7.

## 2. Capabilities (the cross-check list, the design documents and the plans)

| # | Item | Status (measured) | Evidence | Home | Why | Size | Lab | Minimum |
|---|---|---|---|---|---|---|---|---|
| K1 | **ZTP** (P.6; P6_ZTP.md) | built; Lab 9's last step (the heartbeat in Loki) never run on a ZTP device; the responder serves Default's reservations only | `modules/nsot/ztp.py`, `ztp_responder.py` (`_fragment_entries` reads `default_layer`); NSOT_WRITEUP.md: "Lab 9 was not demonstrated within P.6"; C1252 | Core 1.0 | the labs need it first | M | 8, 9 | yes |
| K2 | **Troubleshooting** (LAB_REQUIREMENTS 3.1c; NSOT_PLAN's Lab 10 set) | built for 3.1c's set; Lab 10's set names C38's adjacency alerting "if it has landed", and C589 says an adjacency drop inside two reads raises nothing | `routes/reads_v2.py` (show commands across devices), `modules/history_promq.py`, `history_logq.py`, `routes/logs_v2.py`, Ask the device, path trace; C589 open | Core 1.0 | the lab needs it; C589 is CORE "Now" | M | 10 | yes |
| K3 | **Toolbox** (C762, C1310) | not started | no route or template; ping and traceroute are allowlisted reads (`readonly_commands`) | Core 1.0 for read-only tools (DNS, TCP port, MTU) if Lab 10's handout asks; nmap and packet capture post-1.0 | each active tool is a new third-party licence and an active probe; nmap and packet capture, post-1.0, are each large | M | 10, if its handout asks | yes |
| K4 | **Topology host discovery** (C1309; C806's endpoint locator) | not started | `readers/topology_graph.METRICS` reads LLDP, routes and interface state only; no MAC, ARP or ND | post-1.0 | a new capability, beyond a complete program | L | — | yes |
| K5 | **NetBox browser** (C759, C1308) | partial: the device's NetBox tab and the import jobs | `routes/netbox_v2.py`, `modules/device_netbox.py`; nothing browses sites, prefixes, IPs, VLANs or cables | Core 1.0 | "integrated services: users rarely open NetBox" | L | — | yes |
| K6 | **Integrated services** (Kea, Loki, Grafana in-app) | built: DHCP, Logs, Monitoring panels; Grafana's two role dashboards typed as UIDs in Settings, not picked | `routes/dhcp_v2.py`, `routes/logs_v2.py`, `readers/grafana_dashboards.py`; `_fleet.html` picks a dashboard to view | Core 1.0 for the role-UID picker | "the dashboard selectable, not assumed" | S | — | yes |
| K7 | **Per-feature templates and one-click presets** (C764, P.12) | partial: the monitoring profile is the one feature pack | `modules/nsot/profile.py` SECTIONS; templates per platform only (`modules/nsot/templates/`); no OSPF or BGP pack | Core 1.0 | the operator's ask, network-agnostic; the course's one-click configurations have no written list in the repository (section 7) | L | — | yes |
| K8 | **Config to intent** (C1146; CONFIG_TO_INTENT.md) | designed only | no route; `modules/nsot/seed.py` parses a golden into intent (the building block) | Core 1.0 | deterministic, and the parser exists | L | — | yes |
| K9 | **Runbooks and procedures** (C1147, P.22; RUNBOOKS_PROCEDURES.md) | designed only | no runbook code; no Ansible | post-1.0 | procedures need the bulk frame (K25) and roles (K46) | L | — | yes |
| K10 | **SNMPv3, generated and rotated, one button** (C249; A C139) | partial: one-button profile deploy built; SNMP v2c only | `/v2/monitoring/apply`; `monitoring_coverage.py:34-36` counts `snmp-server community`; `profile_propose` reads the community | Core 1.0 | closes A C139 (the public community); the operator's ask | L | — | yes |
| K11 | **New devices to Prometheus automatically; monitoring in default intent** (C488, C229) | built with limits: targets from Default's layer only; a network with no profile gets no monitoring | `modules/prometheus_targets.py`; onboarding's profile step (`onboard.py:3622`) | Core 1.0 | a new network must be monitored without a setting | M | 9 (the heartbeat arrives) | yes |
| K12 | **Data lake queryable from the GUI** (C405, C406) | partial: the Prometheus and Loki builders built; MinIO and Thanos never read | `modules/history_promq.py`, `history_logq.py`; `integrations/s3_archive.py` writes only | Core 1.0 for Thanos (metrics past 90 days) in the same builder; raw-archive reads post-1.0 | "obvious how to query" holds only to 90 days | M | — | yes |
| K13 | **Flow collection** (FLOWS_DESIGN.md, C1004) | designed only | no collector; `collector_netflow_enabled` is a retiring key with no reader | post-1.0 | a new service and licence | L | — | unmeasured |
| K14 | **Incident evidence export** (C799) | not started | — | Core 1.0 | an enterprise ask the existing stores answer, deterministic | M | — | yes |
| K15 | **ISP delivers the paid-for bandwidth** (C800) | not started | — | post-1.0 | active tests; the lab's C8000v caps at about 10 Mbit/s | L | — | yes |
| K16 | **Bandwidth by application and user** (C801) | not started | — | post-1.0 | needs flows (K13) | L | — | unmeasured |
| K17 | **Port scans** (C803) | not started | — | post-1.0 | nmap's licence; an active probe | M | — | yes |
| K18 | **Suspicious-traffic analysis** (C804) | not started | — | post-1.0 | needs flows (K13) | L | — | unmeasured |
| K19 | **Per-device SSH port** (C805) | not started | port 22 hardcoded: `modules/connection.py:187,448,553`; `host_keys.SSH_PORT` | Core 1.0 | real networks differ; small | M | — | yes |
| K20 | **IPv6 parity on every feature** (C1245; IPV6_PARITY.md) | designed only (an audit: 371 address sites, 109 break, 9 unknown) | IPV6_PARITY.md section 1; nothing run | post-1.0, before Stage 10 | the charter places C1245 FUTURE as its own epic; Core 1.0 features are IPv4-verified. The operator's call: the charter also says IPv4-only is unfinished | L | — | yes |
| K21 | **Drained** (A C551, A C552; NSOT_DRAINED_DESIGN.md) | partial: the interface-counter version, switched off | `modules/drained.py` `ENABLED = False`; no NetBox status read, no counting ACL, no runbook | Core 1.0 (both rows are A), or re-rank C551's measurement | the NetBox status read and the bulk exclusion first (M); the measured traffic (L) | M + L | — | yes |
| K22 | **Pre-deployment validation: Batfish plus own checks** | partial: own checks built; Batfish none | `nmas-config-check`, template approval, intent editor's checks, deploy preview and verify | Phase 8 (8.5), as planned | Batfish serves Translate's routing changes; Java's footprint | L | — | unmeasured, unlikely within 8 GiB beside the stack |
| K23 | **Revert by reload** (NSOT_REVERT_BY_RELOAD.md; B C618, B C563, C564) | not built; the plain Reload is (P.14) | no `boot_file.py`; `reload_op.py` docstring line 6; `tftp_once.py` reached only by a script | Core 1.0 | its rows are B (Phase 2, CORE) | L | — | yes |
| K24 | **Undo a successful change without a reload** (B C531, B C561) | not started | Revert only after a rollback (`intent_ops.block_state`); restore merge-only | Core 1.0 (both B), or re-rank | `configure replace` and measured removal | L | — | yes |
| K25 | **Bulk actions** (C1307; BULK_ACTIONS.md, answered 2026-10-18) | partial: bulk Save, Plan a deploy, Change a setting, Coverage Apply | `templates/v2/_devices.html` selection bar; no batch planner, bulk Reload or guardrails | Core 1.0 | the operator's ask; its questions answered | L | — | yes |
| K26 | **Select-all** (C1304) | built | `device_list.matching`; `_devices.html` tri-state box | done | — | — | — | yes |
| K27 | **Recently cleared screen** (B C1319) | not started; the record is built (C1192) | `modules/attention_record.py`; no screen | Core 1.0 | a B, and the record exists | M | — | yes |
| K28 | **Remote optional: durability** (B C1320) | not started | REMOTE_OPTIONAL.md R14; "no remote" drawn at `remote_publication.py:252` | Core 1.0 | a B; the charter's offline rule | M | — | yes |
| K29 | **Remote optional: any provider** (B C1321) | not started | REMOTE_OPTIONAL.md R1 to R13; `remote.py:224`, `:389-390` | Core 1.0 | a B | L | — | yes |
| K30 | **A remote's commits taken in** (C1315) | not started | `remote_publication` reads only; no fetch | Stage 10 | with the edge kit's offline sync (the operator) | L | — | yes |
| K31 | **Records consolidated** (E18; NSOT_PHASE4_RECORDS_POSTGRES.md) | partial: receipts only | `records_db.STORES = ("receipts",)`; `records_migrate.py`; the other stores are files | Core 1.0 | the charter's one store; Respond's observe records and the prompt record (Phase 8) want it | L | — | yes (in the measured 4.3 GiB) |
| K32 | **GUI completeness** (every capability reachable; every setting and status true) | mostly built | `tests/test_route_reachability.py` (`KNOWN_UNREACHABLE` empty); C1143 (the heuristic can pass a dead route); C1302 (11 screens never compared with their boards); no proof every setting has a reader | Core 1.0 | "complete" means proven | L | — | yes |
| K33 | **In-app manual and "How does this work?"** | built; accuracy open | `modules/manual.py`, 58 pages, 43 `how()` slugs; C337 | Core 1.0 (C337) | the manual must say only what the code does | M | — | yes |
| K34 | **Update from inside the app** | built; host steps still need a terminal; GitHub only | `routes/update.py`, `update_op.py`, `deploy/update/nmas-update`; C1008 | Stage 10 | Docker updates and offline bundles replace it (Stage 10 section 1.6; C1008) | L | — | yes |
| K35 | **Respond, observe mode** (moved from Phase 8's 8.2, 2026-10-18) | not started | no "would have converged" record or false-positive count; `nsot/convergence.py` is verify's settle windows | Core 1.0's tail | the operator's | L | — | yes |
| K36 | **P.8 step 9:** the five per-list files folded into the store | open | PHASE7_BURNDOWN section 1c | Core 1.0 | per-network settings are half-moved | M | — | yes |
| K37 | **P.7 per-series baselines** (C433) | not built | heartbeat and telemetry rules generated; no 7-day p95 baselines | post-1.0 | alert tuning | M | — | yes |
| K38 | **P.11 time travel** (Topology snapshots) | not built | the rest of P.11 is built (`topology_page.py`, `path_trace.py`) | post-1.0 | | L | — | yes |
| K39 | **P.13 software image management** | not started | only `verify /md5` as a read | post-1.0 | | L | — | yes |
| K40 | **P.20 the audit's scans** (CSP on every v2 route, cross-process state, operands, busy states, writeup entries) | not started as scans | per-page CSP tests only | Core 1.0 | they hold the standing rules mechanically | M | — | yes |
| K41 | **P.21 Grafana's declared expiry field** | the rest of P.21 built | `readers/credential_health.py` | Core 1.0 | small | S | — | yes |
| K42 | **Common asks** (C806: fleet config search, CVE and end-of-life, STIG and CIS, capacity, availability, asset report) | proposals | ASSURE_FEATURES.md section 7 | post-1.0 | | L | — | yes |
| K43 | **Sites within a network** (C1003; SITES_DESIGN.md) | designed only | — | post-1.0 | | L | — | yes |
| K44 | **Deploy follow-up window** (B C60) | not started | `receipts.FOLLOW_UP_NOT_BUILT` | Core 1.0 (B), or re-rank | a second reading after a deploy, deterministic | M | — | yes |
| K45 | **The device as witness of its own changes** (B E6: archive, log config, notify syslog) | not started | `parsers/base.py:268` keeps it unmodelled | Core 1.0 (B), or re-rank | | L | — | yes |
| K46 | **Sign-in and roles** (9.I; Stage 10 sections 2 and 3; local accounts, OIDC, AD) | not started | `modules/identity.py` trusts the access proxy's assertion only; `may()` has no roles | Stage 10 | the operator's path | L | — | yes |
| K47 | **Multi-vendor and the platform layer** (9.P; Stage 10 section 12) | not started | `platform.DIALECTS` holds two Cisco dialects | Stage 10 | | L | — | yes |
| K48 | **gunicorn behind nginx** (9.S; Stage 10 section 4.1) | not started | `app.py:630` runs Werkzeug | Stage 10 | | M | — | yes |
| K49 | **Docker and the install script** (Stage 10 section 1) | not started | systemd units only (`deploy/systemd/`) | Stage 10 | | L | — | yes |
| K50 | **The first-run wizard** (Stage 10 section 5) | not started | — | Stage 10 | | L | — | yes |
| K51 | **The separate repository, its export and its licence** (Stage 10 section 8) | not started | no LICENSE at the root | Stage 10 | | M | — | yes |
| K52 | **OpenBao on the same host** (C733; CREDENTIAL_STORE_REDESIGN.md) | designed only | `secrets_store.py`, one Fernet key | Stage 10 | | L | — | unmeasured |
| K53 | **Device-login 2FA** (PUBLIC_RELEASE section f) | designed only | — | Stage 10 | | L | — | yes |
| K54 | **The edge-kit manager** (C1005; EDGE_ARCHITECTURE.md) | designed only | — | Stage 10 | | L | — | yes |
| K55 | **IPAM import from a spreadsheet** (C1006; IPAM_IMPORT_DESIGN.md) | designed only | no spreadsheet library | Stage 10 | a new licence | L | — | yes |
| K56 | **Bring-up from provider documents** (C1007; BRINGUP_FROM_DOCUMENTS.md) | designed only | — | Stage 10 | needs the local model | L | — | no: the local model is Large |
| K57 | **Multiple AI providers and the local model** (C1013; PHASE8_PLAN section 10) | designed only | no AI code (removed in D15) | Stage 10 | the release gate (PHASE8_PLAN 13.1) | L | — | no: Large |
| K58 | **Offline install and update** (C1008; OFFLINE_OPERATION.md) | designed only | — | Stage 10 | offline-first is the release's gate | L | — | yes |
| K59 | **Stage 9's lab-safe hardening** (C39/C141, C432, C438, C457, E3, and 9.x) | not started | open rows; T11 below | Stage 10 | "(L) safe here because it is a lab" | L | — | yes |
| K60 | **Bulk onboarding; support tiers per device** (Stage 10 section 7.3) | not started | single-device adopt only (`adopt.py`) | Stage 10 | | L | — | yes |
| K61 | **P.15's rest, P.16's job machinery, P.17's classic-IOS ZTP** | partial / not started | CONCURRENCY_AUDIT.md; no job framework; `onboard.BLOCKED_PENDING_MEASUREMENT` empty | Stage 10 | before 9.S and multi-vendor | L | — | yes |
| K62 | **The rename to Mercury, the trademark search, the lab-tooling area** (Stage 10 sections 6.0a, 7.3) | partial / not started | `lab/` exists; `scripts/nmas-*` names | Stage 10 | at the release | M | — | yes |
| K63 | **SDN controllers** (P.19, Floodlight among them) | not started | no code | Stage 10, last | the operator's order | L | — | yes |
| K64 | **Phase 8: 8.0 (shrunk, PHASE8_PLAN 13.2) and feature 1** | not started | no AI code | Phase 8 | | L | — | yes (hosted) |
| K65 | **Phase 8: features 7, 2, 3, 5, the rest; Respond's classes enabled** | not started | — | Phase 8 | PHASE8_PLAN 13.3's order | L | — | yes (hosted) |
| K66 | **Pre-made "mutation" testing nights** (the parked runner) | parked | `.github/workflows/mutation-nightly.yml` dispatch only | post-1.0 | parked by the operator (C835) | M | — | yes |

## 3. The open A, B and UNKNOWN rows

**A (5):**

| Row | What | Status (measured) | Evidence | Home | Size |
|---|---|---|---|---|---|
| C139 | retired r5's credentials kept in NetBox; the community still `public` | partial: masking built, rotation not | `retire._mask_facts`; `removal.py:125` | Core 1.0 (K10) | M |
| C552 | Drained's 10 pkt/s floor marked every device drained | mitigation built (off) | `drained.ENABLED = False` | Core 1.0 (K21) | M |
| C551 | Drained must be measured | designed only | NSOT_DRAINED_DESIGN.md | Core 1.0 (K21), or re-rank | L |
| C781 | weakly tested helpers (mutation survivors) | partial | `tests/test_goldens_resolution.py`; the rest needs a night | Core 1.0, or re-rank: mutation is parked (C835) | M |
| C842 | a mutant read as survived through selection by import | built, awaiting a night | `scripts/nmas_mutation.py` reach_fresh | Core 1.0, or re-rank (parked) | S |

**B (19, E6 among them):**

| Row | What | Status (measured) | Evidence | Home | Size |
|---|---|---|---|---|---|
| C7 | settings erasure; no "frozen at an old default" classifier | partial | `installation_settings._origin` | Core 1.0 | M |
| C60 | deploy follow-up window | not started | `receipts.FOLLOW_UP_NOT_BUILT` | Core 1.0 (K44), or re-rank | M |
| C230 | Grafana token holds Editor | checker built; the host's token unread | `scripts/nmas-integration-accounts` | Core 1.0 (the operator's one-time step) | S |
| C472 | live regions lose a person's state (deferral accepted) | partial | History diff, remote answer, Coverage scroll open | Core 1.0 | M |
| C531 | cannot undo a success | partial | `intent_ops.block_state` | Core 1.0 (K24), or re-rank | L |
| C554 | Mode B never matches an IPv6 ACL entry | not started | `removal._in_context` (l.212) | Core 1.0 | M |
| C556 | NetBox owns device existence (Planned to Active, retire to Decommissioning) | partial | `onboard.py:323`; retire writes no status | Core 1.0 | M |
| C559 | NetBox import's create path writes "Unknown" and a text platform | partial | `netbox_client._upsert_device` | Core 1.0 | S |
| C561 | restore by `configure replace` | not started | `deploy.py:19` comment | Core 1.0 (K24), or re-rank | L |
| C563 | TFTP reply address | built; host measurement owed | `ztp_responder` IP_PKTINFO | Core 1.0 (K23) | S |
| C618 | the one-shot TFTP and the responder both want udp/69 | designed only (board signed) | no register socket | Core 1.0 (K23) | M |
| C792 | mutation night: cross-test state | partial | conftest clears op_progress | Core 1.0, or re-rank (parked) | M |
| C822 | a patched `time.time` is the process's clock (deferral accepted) | not started | four test files | Core 1.0 | M |
| C828 | Query's Code mode does not read back (deferral accepted) | not started | `history_promq` parses only its own tokens | Core 1.0 | M |
| C834 | mutation night at plan size | built; a night owed | `nmas_mutation.plan(cap=)` | Core 1.0, or re-rank (parked) | S |
| C1319 | no Recently cleared screen | not started | K27 | Core 1.0 (K27) | M |
| C1320 | the "no remote" nag | not started | K28 | Core 1.0 (K28) | M |
| C1321 | a remote works only if it is GitHub | not started | K29 | Core 1.0 (K29) | L |
| E6 | the device as witness of its own changes | not started | K45 | Core 1.0 (K45), or re-rank | L |

**UNKNOWN (50).** Each is a measurement owed, and its size is the measurement's. Six are already
confirmed as gaps in the code, and may become B: C1231, C1279, C597, C581, C997 and C248. The
proposal measures those six in Core 1.0 (S each). The rest are measured as they come (post-1.0,
S each). The LAB ones (C523, C301, C998, C1318) are measured at a lab redeploy. The mutation
ones (C864, C844, C796) wait for the parked runner.

| Row | What | Status / the measurement owed | Home | Size |
|---|---|---|---|---|
| C1231 | `bulk_intent.known_top_level` lacks `profile_exclude` | gap confirmed (l.65 vs `config_check.MERCURY_KEYS`); one bulk preview | Core 1.0 | S |
| C1279 | a deploy to a device gone from NetBox | gap confirmed (`routes/deploy.py` never calls `is_stale`); a test on the shared fake | Core 1.0 | S |
| C597 | `save_golden` refuses a batch for one unmanifested device | gap confirmed (`repo.save_golden` l.1044-1055); host count | Core 1.0 | S |
| C581 | `verify /md5` may outrun the read bound | gap confirmed (`readonly_commands.bound_seconds`); one run on r2 | Core 1.0 | S |
| C997 | the updater does not re-ask about held devices before restart | gap confirmed (`nmas-deploy` asks once); the gap's length | Core 1.0 | S |
| C248 | nothing but the access proxy fronts mutating routes | Werkzeug (`app.py:630`); the cookie's SameSite | Core 1.0 | S |
| C469, C156, C763, C802, C863, C196, C517, C546, C962, C454, C448, C627, C862, C749, C753, C745, C859, C880, C875, C922, C924, C890, C897, C958, C959, C977, C1094, C1098, C1107, C1230, C1214, C1215, C1216, C1102, C564, C567, C549 | 37 rows: each its own measurement (the register names it) | measurement owed | post-1.0 | S each |
| C523, C301, C998, C1318 | 4 LAB rows | at a lab redeploy, or a day of pidstat (C1318) | post-1.0 (LAB) | S each |
| C864, C844, C796 | 3 mutation rows | at the parked runner's next night | post-1.0 | S each |

6 + 37 + 4 + 3 = 50, the register's UNKNOWN count.

## 4. The C rows (458), by theme

C rows are not A or B, so under the definition they may stay open at Core 1.0's finish. Each
theme is post-1.0, unless a Core 1.0 capability (section 2) names its rows. Sizes are for the
whole theme.

| Theme | Rows | C-numbers | What | Home | Size |
|---|---|---|---|---|---|
| T1 Scheduled out of the register | 41 | C462 C461 C332 C290 C254 C269 C252 C189 C250 C247 C249 C245 C229 C212 C178 C173 C171 C168 C150 C164 C14 C25 C38 C88 C58 C63 C92 C102 C106 C133 C105 C30 C2 C5 A2 A3 A4 D1 D7 D9 D10 | owned by a stage (7.x, 8, 9, 10, P-items) | post-1.0, as scheduled (C38 for Lab 10, C249 in K10 and C229 in K11 are Core 1.0) | L |
| T2 Roadmap, designed or proposed | 28 | C750 C759 C764 C762 C1003 C1004 C1005 C1006 C1007 C1146 C1147 C1245 C1008 C1013 C1307 C1308 C1309 C1310 C575 C582 C562 C799 C800 C801 C803 C804 C805 C806 | the capabilities of section 2 | counted in section 2 | — |
| T3 Test harness, CI, gate, mutation, register tooling | 60 | C162 C782 C810 C952 C865 C866 C843 C845 C599 C206 C41 C45 C47 C71 C72 C528 C480 C879 C870 C871 C920 C847 C990 C993 C1080 C1087 C1143 C1163 C1169 C1170 C1172 C1173 C1174 C1175 C1176 C1177 C1227 C1244 C1280 C1281 C1289 C1290 C1291 C1292 C1293 C1288 C1286 C1266 C1265 C1257 C1250 C1251 C1239 C1242 C1218 C1212 C1164 C1139 C1101 C1103 | order-dependent tests, fakes, Lab 7's mechanisations (C1289 to C1293), branch protection (C1164) | post-1.0; C1143 in Core 1.0 (K32) | L |
| T4 Fidelity against signed-off boards | 8 | C919 C942 C1302 C1312 C1295 C1297 C1301 C1125 | screens against their boards; the 11 never compared (C1302); stale boards (C1312) | Core 1.0 (K32) | L |
| T5 v2 wording, visual, layout | 53 | C526 C338 C183 C179 C915 C916 C917 C918 C926 C887 C929 C899 C901 C1015 C1021 C1017 C938 C861 C851 C921 C853 C830 C814 C985 C1088 C1142 C1228 C1233 C1234 C1298 C1299 C1300 C1241 C1130 C1119 C1120 C1034 C1035 C1042 C1043 C1046 C1047 C1049 C1050 C1051 C1054 C1055 C1057 C1060 C1061 C1062 C1066 C1068 | copy, labels, phone width, raw exceptions shown | post-1.0 | L |
| T6 v2 functional gaps in screens | 36 | C537 C538 C372 C447 C473 C704 C872 C914 C928 C889 C903 C904 C907 C812 C976 C1283 C1282 C1296 C1275 C1213 C1156 C1157 C1137 C1129 C1044 C1045 C1048 C1052 C1053 C1056 C1063 C1064 C1070 C1071 C1072 C1073 | missing controls: sort (C704), retry, search, findability | post-1.0 | L |
| T7 NetBox correctness | 21 | C641 C665 C1019 C1020 C1009 C1097 C1099 C1100 C1224 C1226 C1254 C1249 C1124 C1117 C1118 C1036 C1037 C1038 C1039 C1040 C1041 | NetBox integration details | post-1.0 | L |
| T8 Monitoring, Grafana, Loki, Prometheus, readers | 24 | C589 C603 C13 C376 C534 C535 C530 C404 C405 C406 C722 C891 C892 C951 C969 C970 C971 C966 C1014 C829 C831 C1261 C1032 C1069 | adjacency (C589, Lab 10), retention, Loki's device label (C722) | post-1.0 (C589 in K2, and C405 and C406 in K12, are Core 1.0) | L |
| T9 Needs attention | 11 | C366 C488 C909 C911 C893 C894 C1186 C1314 C1110 C1058 C1059 | duplicate rows, raw exceptions, wording | post-1.0 (C488 in K11 is Core 1.0) | M |
| T10 History, records, audit attribution | 21 | C237 C364 C365 C367 C368 C360 C361 C895 C896 C898 C1002 C846 C848 C849 C1085 C1090 C1104 C1106 C1178 C1114 C1031 | Source and kind, per-device records | post-1.0 (E18's rows C237, C360, C361, C364, C365 and C368, in K31, are Core 1.0) | L |
| T11 Credentials, secrets, hardening | 18 | C451 C733 C211 C218 C220 C235 C333 C348 C455 C457 C407 C590 C438 C432 C900 C1000 E3 E5 | Fernet key, MinIO root, enable secret, roles | Stage 10 (K52, K59) | L |
| T12 Lab devices and the lab | 9 | C93 C94 C673 C671 C525 C695 C703 C950 E2 | s3, RIP, LLDP, r3 and r4 | post-1.0 (LAB) | M |
| T13 Deploy, restore, intent, verify | 23 | C596 C186 C6 C113 C238 C484 C518 C506 C490 C325 C334 C339 C427 C445 C725 C939 C983 C984 C994 C1229 C1284 C1285 C1065 | restore and baseline correctness; C325 and C334 are revert by reload's | post-1.0 (C325 and C334, in K23, are Core 1.0) | L |
| T14 Multi-network scoping, data folders | 22 | C159 C161 C208 C910 C499 C972 C973 C329 C396 C956 C937 C1079 C1081 C1082 C1092 C1093 C1095 C1096 C1185 C1140 C1141 C1113 | Default-only reads, folder-creating reads | post-1.0 (C159, in K31, is Core 1.0) | L |
| T15 Docs, stale text, dead code | 20 | C586 C592 C337 C960 C999 C1001 C967 C968 C1012 C816 C996 C980 C1084 C1091 C1144 C1162 C1219 C1311 C1154 C1155 | DEPLOY_LINUX, the manual, unused settings | post-1.0 (C337, in K33, is Core 1.0) | M |
| T16 Performance, scale, concurrency | 17 | C202 C912 C322 C450 C876 C877 C858 C925 C992 C989 C995 C978 C1184 C1247 C1262 C1111 C1033 | SSH pool, per-device work, load times | post-1.0 (Standard's 1,000 devices is a target, unmeasured) | L |
| T17 W4's screen notes | 18 | C1194 to C1211 | onboarding, adopt, abandon, deploy | post-1.0 | M |
| T18 Host operations, backup, update | 11 | C144 C145 C40 C44 C241 C355 C545 C623 C1112 B9 B10 | backup proof, keys, pip reproducibility | post-1.0 | M |
| T19 DHCP, ZTP, onboarding | 8 | C216 C483 C697 C1236 C1237 C1238 C1252 C1217 | lease release, Kea per network, post-ZTP staleness | post-1.0 (C1252 and C483, in K1, are Core 1.0) | M |
| T20 Lab-specific values in the product | 3 | C336 C965 C979 | a lab domain default, lab names | Core 1.0 (the charter's rule) | S |
| T22 Git remote, publication | 6 | C328 C946 C1075 C1076 C1011 C1315 | GitHub reachability, push tags | Core 1.0, with K28 and K29 (C1315 is K30, Stage 10) | M |

Total: 41 + 28 + 60 + 8 + 53 + 36 + 21 + 24 + 11 + 21 + 18 + 9 + 23 + 22 + 20 + 17 + 18 + 11 + 8 + 3
+ 6 = 458 (the survey placed every C-numbered row once, by a script check).

## 5. ZTP against P6_ZTP.md's acceptance for Labs 8 and 9

P6_ZTP.md section 6, "Acceptance: Labs 8 and 9, on a throwaway". Each criterion is listed with its
measured state. Runs are named from the records that hold them.

| Criterion (P6_ZTP.md) | Code | Run on a ZTP device |
|---|---|---|
| **Lab 8:** a node booted with no configuration "is leased an address from a reservation the TOOL wrote" (l.318) | built: `ztp.write_reservations` (l.531) under a lock, Kea config-test, reload, read back; `plan_check` refuses conflicts and the forbidden options | yes: bp-ztp-a (2026-09-27), tw-ztp-a on v2 (2026-10-05), s5 and s6 in W4 (2026-10-17) |
| "fetches its bootstrap config from the tool, recorded as a reveal row naming its address and the hash of what was served" (l.319-320) | built: `ztp_responder.decide` (l.117) and `record` (l.164) | yes: the same runs |
| "is reached by the tool with the staged credential" (l.321) | built: `/v2/onboard/<name>/verify` | yes |
| "Each of those is observed from its own source" (l.323) | built: `ztp.progress` reads Kea's reservation, Kea's lease and the responder's audit | yes |
| **Lab 9:** "Phase 2: rotation, RW removal, a true first golden, NetBox, and promotion" (l.327) | built: `onboard.run_phase_two` | yes: bp-ztp-a, tw-ztp-a, s5 (W4) |
| "one intent deploy, which lands the P.1 syslog block; the heartbeat then arrives in Loki" (l.328-329) | built: the block arrives through the network's monitoring profile (phase 2's profile step) | **NOT shown.** Intent deploys ran on tw-ztp-a and s5, but no record shows a ZTP device's heartbeat arriving in Loki. tw-ztp-a's network had no profile (C488), and NSOT_WRITEUP.md says "Lab 9 was not demonstrated within P.6" |
| "Infrastructure as code is literal" (l.331-332) | built: committed intent, an approved template, a confirmed program | the template approval on v2, 2026-10-05 |

**What ZTP still needs for the labs** (K1, all in Core 1.0, lab first):
1. **One Lab 9 run end to end:** on a network whose monitoring profile is set, a ZTP device's
   heartbeat is read in Loki. A walk, S. It depends on K11's default profile, or on setting
   the profile by hand first.
2. **C1252:** the responder serves Default's reservations only. If the lab's network is not
   Default, its devices are refused. M.
3. **C563:** the reply address, a host measurement (S). C618 (udp/69) matters only if revert
   by reload runs beside ZTP.
4. **Stated not proven, and not needed by the lab** (P6_ZTP.md l.334-340): a relayed path,
   physical hardware, PnP option 43, Python ZTP, the bulk job. C1245: ZTP is IPv4-only.

## 6. Core 1.0, signed off (the operator's triage, 2026-10-18)

**The operator's triage of this inventory, 2026-10-18.** Everything below was accepted as
proposed except these changes:

1. **K24, undo without a reload, moves to post-1.0.** C531 and C561 are re-ranked B to C, by the
   operator's decision of 2026-10-07: a revert is startup config plus a reload for now, and
   no-reload reverts come later. K23 stays in Core, with C618 before it.
2. **K29, any remote provider, moves to Stage 10.** C1321 is re-ranked B to C: the local
   repository is the source of truth, so a GitHub-only remote limits the public release, not
   Core. K28, durability, stays in Core.
3. **The mutation rows are re-ranked:** C781 and C842 from A to C, and C792 and C834 from B to C.
   **But un-parking the runner (C835) joins K32:** Core 1.0 is not signed off without a mutation
   pass over the modules Core 1.0 adds or changes. Lab 7's rules apply: one mutant at a time,
   behind the canary, and every survivor either killed by a test or recorded.
4. **IPv6 (K20).** The 109 existing break sites stay a post-1.0 epic, before Stage 10's release
   gate. From now on, every Core capability that handles addresses is built and tested to work
   on an IPv6 management address as well as IPv4. That is a standing rule
   (docs/IPV6_PARITY.md, "The standing rule"). Each item's size absorbs the cost. None moves
   to a larger size: the address-handling items are K11, K19, K21, K23, K5 and K10, and K21,
   K23, K5 and K10 are already L. K23 grows most inside L, since its one-shot TFTP and boot
   path must serve an IPv6 address.
5. **K22, Batfish, stays in Phase 8 as an optional add-on:** Standard tier and up, never
   required. A Minimum install validates with Mercury's own checks alone.
6. **K7, the feature packs' starter list:** OSPF, BGP, VRRP, NTP, AAA and local users, and VLANs
   and trunks (monitoring exists). Each pack is a per-feature template rendered from intent,
   previewed and confirmed by hash, network-agnostic and keyed by platform. If the course gives
   a list, it replaces this one.
7. **"No repo assigned" is dropped.** It was a paraphrase, not screen text.
8. **K21, Drained, is in Core whole:** the NetBox status read and the bulk exclusion first, then
   the measured traffic. Both rows, C551 and C552, stay A.
9. **K3 waits for Lab 10's handout.** The operator will supply it.

**The capability list.** **Must-have (21):**
1. K1 ZTP for Labs 8 and 9
2. K2 troubleshooting for Lab 10, with C589
3. K3's read-only tools, when Lab 10's handout says
4. K11 monitoring automatic per network
5. K28 remote durability
6. K31 records consolidated
7. K27 Recently cleared
8. K25 bulk actions
9. K10 SNMPv3
10. K21 Drained, whole
11. K5 NetBox browser
12. K6 dashboard picker
13. K8 config to intent
14. K7 feature packs (the starter list above)
15. K23 revert by reload, C618 first
16. K12 Thanos in the builder
17. K19 the SSH port
18. K32 completeness proven, with a mutation pass over Core 1.0's modules
19. K33 the manual true
20. K36 P.8's step 9
21. K41 P.21's field

Plus K35, Respond's observe mode, in the tail.

**Should-have, below the cut line (4):**
- K14 evidence export
- K40 P.20's scans
- K44 the follow-up window (B C60)
- K45 the device as witness (B E6)

If the re-forecast after the first four capabilities shows the box will not hold, they move to
post-1.0, with their B rows re-ranked for that reason. That is the operator's call.

**Plus no open A or B:** the A and B rows left after the re-ranking (A 3: C139, C551, C552; B
14). Each is folded into a capability above, or closed on its own: C7, C230, C472, C554, C556,
C559, C822 and C828.

**The order** (the operator's, 2026-10-18; lab need first, then dependency):
1. **K1, ZTP.** C1252 first: the responder serves every network's reservations, not only
   Default's. Then Lab 9's last step: a ZTP device's heartbeat arriving in Loki, run for real on
   the host. K11 comes with it where Lab 9 needs it: a network with no profile still gets
   monitoring.
2. **K2, troubleshooting, with C589.**
3. **K11's remainder, then K31, K28 and K25,** and onward:
   - K21, K10 and K19;
   - K23 (C618 first);
   - K5, K6 and K12;
   - K8 and K7;
   - K27;
   - K32, K33, K36 and K41;
   - the should-haves if the box holds;
   - K35 last, so its clock runs into Phase 8.
   K3 is built when Lab 10's handout arrives.

**Stop and report:**
- after K1, with Lab 9's heartbeat shown in Loki and its evidence;
- after the first four capabilities, with the time box re-forecast from their measured pace
  only, and whether the cut line holds;
- whenever a lab handout is needed.

**The time box, recomputed with the triage** (S 1 to 2 h, M 2 to 8 h, L 8 to 24 h; mid S 1.5,
M 5, L 16; the L ceiling is an assumption):

| Part | S | M | L | Low | Mid | High |
|---|---|---|---|---|---|---|
| **Must-have** | 10 | 17 | 11 | 10 + 34 + 88 = **132 h** | 15 + 85 + 176 = **276 h** | 20 + 136 + 264 = **420 h** |
| **Should-have** | 0 | 3 | 1 | 6 + 8 = **14 h** | 15 + 16 = **31 h** | 24 + 24 = **48 h** |
| Both | 10 | 20 | 12 | 146 h | 307 h | 468 h |

**What the counts hold:**
- **Must-have:**
  - the capabilities: S 2 (K6, K41); M 11 (K1, K2, K3, K11, K28, K27, K21's NetBox part, K12,
    K19, K33, K36); L 10 (K31, K25, K10, K21's measurement, K5, K8, K7, K23, K32, K35);
  - the mutation pass added to K32: L 1;
  - the A and B rows not folded into a capability: S 2 (C230, C559), M 6 (C7, C472, C554, C556,
    C822, C828);
  - the six UNKNOWN measurements confirmed as gaps: S 6.
- **Should-have:** M 3 (K14, K40, K44), L 1 (K45).
- **The box** is the mid figure: **about 280 hours of agent work for the must-have, and 31 more
  for the should-have.** It is re-forecast after the first four capabilities, from their
  measured pace only (CLAUDE.md, writeup forecasts).
- **No calendar figure** is derived from the sizes (Phase 7's entry).

**Landed** (section 2's Status column stays the survey's snapshot; each landing is here). The
re-forecast after the first four takes their pace from these commits' times only: the span
from the triage's commit (b7988607, 2026-10-19 02:34 UTC) to the fourth one's push, gates and
deploys included. No start time is recorded for any one item, so no per-item figure is drawn.

| # | Size | Commit | Pushed (UTC) | What landed | Left |
|---|---|---|---|---|---|
| K1 | M | 1b66ad96 | 2026-10-19 02:46 | C1252: the responder serves every network's reservations; K11's inheritance (a network with no profile takes Default's) | Lab 9's last step, the operator's W5 sitting (docs/walks/W5.md) |
| K2 | M | 63cc648d | 2026-10-19 03:12 | C589: one Needs attention row per adjacency a device logged down, acknowledged within its band | none in Core 1.0 (C1322, C1323 registered) |
| K11 | M | d244d7b1 | 2026-10-19 03:31 | the remainder: one set of targets, one record and one job-health row per Prometheus owner; two owners naming one directory refused (C229 closed) | none |
| K31, part 1 | (L) | c9aeef2c | 2026-10-19 04:00 | E18's record rows: C365 (an intent edit named as one), C361 (a rotation row names its network), C364 (a scoped batch held and recorded as its scope), C368 (a withdrawal drawn with who and why), C237 (one labelled host login), C360 (the heartbeat re-measure in History; History's gaps at 0); the record stores surveyed (C1324 to C1329 registered) | the stores into the records database, one line-store machinery for the 17 append-only stores (the survey's), then the document stores; C159 |
| K31, part 2a | (L) | 38c09beb | 2026-10-19 04:10 | the migrator, the card, the routes and the records-check reader per store (`records_migrate.LineStore`, receipts the first); behaviour for receipts unchanged | each line store joined to it, its owner's read and write on its backend (C1324 first) |
| K31, part 2b (1) | (L) | this commit | | acknowledgements, the second line store (one file for the installation): its read and write on its backend, its own switch, moved and moved back by the card; a write the database does not take is refused, the row staying | the other 15 line stores, one at a time |

## 7. Not placed, and missing from the cross-check list

- **"Perigo's one-click pre-made configurations":** no list of them exists in the repository.
  "Perigo" appears only as the course's instructor (NSOT_PLAN.md line 27,
  `golden_state.py`). They are folded into K7 (feature packs). Their list must come from the
  course material when the operator supplies it.
- **"No repo assigned":** dropped by the operator, 2026-10-18 (a paraphrase, not screen text).
- **Requests in the register not on the cross-check list** (the survey's part C), each placed
  in a theme above:
  - C1003 sites; C1008 offline; C697 releasing a DHCP lease; C704 sortable Devices columns;
    C427 a device's designed role checked; C575 a "device under load" warning;
  - C589 adjacency (in K2); C596 startup differs from running; C1261 the trap path watched;
    C722 Loki's device label; C1311 console noise; C1302 the unwalked screens (in K32).
- **Lab 10's handout:** locked. K2 and K3 are mapped from NSOT_PLAN's Lab 10 set, not from the
  handout. When the operator supplies it, its objectives go in docs/LAB_REQUIREMENTS.md and K3
  is decided.
