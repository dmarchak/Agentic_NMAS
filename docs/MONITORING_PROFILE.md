# The monitoring profile (NSOT_PLAN P.9): designed 2026-09-30, DECIDED the same day; steps (a) and (b) built

The operator's requirement (2026-09-30): every device, new and existing, carries the
configuration its integrations need (SNMP, syslog, the heartbeat, NTP, LLDP and CDP, the
routers' telemetry, IP SLA), derived from the connectors the network uses, with one owner.

## 1. Why

- **r6.** It became an SNMP target when the targets were generated from the inventory
  (C232), and Grafana's "Device unreachable (SNMP)" fired. That was false: r6 answers SSH
  and its heartbeat, and its configuration has no SNMP. Since 2026-09-30 a device is a
  target only when its committed golden configures SNMP, and a device missing an
  integration the network uses is a Needs attention row (`modules/monitoring_coverage.py`):
  "r6 is not monitored by SNMP". That row's action, "Apply the monitoring profile", is what
  this document designs.
- **Three mechanisms for one block today.** P.1's syslog and heartbeat block is written
  into intent by onboarding (`onboard.py`), never emitted by the bootstrap, and dropped by
  seed (C216, decided "seed keeps declared blocks"). The fleet's SNMP lines were written by
  hand, device by device. Nothing gives a new device either.
- **Every new device repeats r6** until this exists.

## 2. The model

**A profile is per network, and committed.** It is one document in the list's own
repository, `config_repo/profiles/monitoring.yml`, changed by a commit
(`profile: <summary>`, `Source: profile`), read at HEAD like every other record (C104).
Being in the list's repository makes it per network with no new store. The connector
settings it derives from become per network with P.8.

**It holds data, never configuration text.** Each section has the shape the parsers
already emit into `host_vars` (`snmp`, `logging.syslog`, `ntp_servers`, the `lldp run` and
`cdp run` FLAGS under `flags` (C253: this line once said `lldp` and `cdp`, a shape no parser
writes),
`telemetry`). The PLATFORM TEMPLATES render it, so IOS and IOS-XE syntax differences stay
where they already live, and nothing in the profile is platform text. A section carries
`platforms:` where it applies to some platforms only (telemetry: `cisco_iosxe`) and
`roles:` where it applies to some roles only (IP SLA policy: `router`). That makes C225's
role data load-bearing, and it is corrected through `modules/inventory_edit.py`.

**The connectors are the PRIMARY source, built 2026-09-30** (the operator: step (b)'s first
version proposed only what the fleet's intent already agreed on, which is circular, and a
network the tool has never seen has nothing to agree on). `profile_propose.connector_value()`
derives each section from its connector's settings:
- syslog and the heartbeat from `syslog_host`, `syslog_trap_level`, `syslog_origin_id`,
  `syslog_source_interface` and `syslog_heartbeat_seconds`;
- SNMP from snmp_exporter's auth module (`snmp_exporter_config`, `snmp_exporter_auth`: the
  community it polls with, read in memory and never shown) and `snmp_trap_host`;
- NTP from `ntp_servers`;
- telemetry from Telegraf's listener (`telemetry_receiver`), with the fleet's measured
  subscriptions, IOS-XE only;
- LLDP from the lldp scrape.

The fleet is then the CROSS-CHECK. A device holding another version is named with what it
gains and what it keeps (its own value wins), and a device whose own stored secret differs is
named (values never shown). A section whose connector is empty falls back to what the fleet
agrees on, and its basis says so. CDP has no connector. **Onboarding applies it (step (c),
2026-10-01):** Verify is a preview and a confirm. The preview reads the pending device and
computes the profile's program from its CAPTURE (`profile_apply.for_capture`: its own parse
rendered alone and with the profile, since its intent is only the bootstrap); phase 2 recomputes
the fingerprint from its own capture, sends nothing at all if it moved, sends the program after
the RW removal and before the save and the first golden, and reads it back. A template that does
not reproduce the device sends no profile and says so (the device is onboarded, and Apply
remains); a line the parser does not model is named and never blocks, since the program never
touches it. **Adopt applies it too** (the same day): its preview computes the program from the
capture it reads with the supplied credential, lists it masked in the program and binds it in the
fingerprint; the apply sends it after the accounts and before the save, reads it back, and the first
golden records it. A value the device sets differently is kept (the device overrides the profile).
**(d), the screens, began 2026-10-01:** Monitoring opens on the fleet Grafana dashboard
(`/v2/monitoring`, `grafana_fleet_dashboard_uid`), with Coverage as a tab beside it. Coverage (`/v2/monitoring/coverage`,
`monitoring_coverage.fleet()`) draws each device by integration from its committed golden, each
cell decided on the server (configured; missing and the profile supplies it; missing and it does
not, saying why; excluded with the reason; not used by the network; the profile's section scoped
away from its platform or role; unknown when the golden cannot be read). The devices the profile
applies to are offered, ticked where it supplies a gap, and the form opens the batch preview
for the ticked devices. **(d2), built 2026-10-01:** the preview, confirm and result in v2
(`/v2/monitoring/apply`, `routes/v2.py`), drawn server-side from the six parts the deploy plan
builds (`routes.deploy.plan_devices` with scope `profile`): the ROLLOUT ORDER drawn and set on
the page (earlier, later, leave out), each device's exact program masked, what is in place and
held back, each superseded line with its box and, once ticked, its reason field (a device with
a ticked line and no reason is not confirmable), gates and operands one level down. The confirm
starts the batch as a JOB (`modules/deploy_job.py`) in that order, as the verified person,
through `routes.deploy.apply_batch` (the one apply); the page draws where it is, device by
device, as each finishes, then the result from the receipts. **(d3), built the same day:** the
device page's Monitoring tab opens with "Monitored by", Coverage's own cells for that device
(`routes/device_v2._monitored_by`), and "Apply monitoring profile…" where the profile supplies a
gap, opening the same preview for that device alone.

**Each section names the connector it is derived from,** and is ABSENT while that
connector is not configured. "Configure a connector, and devices get the matching config"
then means: configuring the connector proposes the section (a preview of the profile
commit). It never writes itself.

| Section | Derived from | What the profile holds |
|---|---|---|
| SNMP | Prometheus configured; the community snmp_exporter's auth module speaks (`public_v2` today) | `communities: [{ref: snmp_community_ro, access: RO}]`, the trap host (the NMAS's trap receiver address), location and contact (per-network settings) |
| Syslog | Loki configured; the syslog receiver's address (the host's rsyslog, which writes `/var/log/network/<address>.log` for Promtail) | `hosts`, `trap: notifications`, the source interface RULE (below) |
| Heartbeat | the heartbeat alert rules exist (P.1's, P.7's generated ones) | `heartbeat: 300` (the NMAS-HEARTBEAT applet) |
| NTP | a per-network setting (no connector) | `ntp_servers` |
| (all) | Fields are SHARED (must agree; a person chooses a version when they differ) or PER-DEVICE (SNMP `location`, `contact`, `chassis-id`: never compared, never in the profile, never overwritten); `snmp.settings` merges entry by entry (C255) | |
| LLDP, CDP | always (the topology and the `lldp` job read them) | `flags: {"lldp run": true}`, `flags: {"cdp run": true}`; applied only to the platforms whose devices write the line, and an absent line read from the MEASURED defaults (`modules/nsot/platform_defaults.json`, C254) |
| Telemetry | the Telegraf endpoint, a new per-network setting (it is not a setting today) | the fleet's measured subscriptions (101 CPU, 102 interfaces), receiver from the setting; `platforms: [cisco_iosxe]` |
| IP SLA | a POLICY, never addresses (section 6) | `policy`, `type`, `frequency`; `roles: [router]` |

**Secrets are references, owned by the network.** The profile's community is
`snmp_community_ro`, and its value is held once per network under a profile-scoped key
built by ONE function (`credentials.profile_secret_key(list)`), beside
`template_secret_key()`. `hydrate_secrets()` resolves a device's own value first, then the
profile's. This settles C235 for the monitoring secrets: a new device inherits the value
without a per-device copy. **It revises C139's rule** ("each device's own secret"), which
came from a transition in which devices held different values. The profile's value is the
owner, and a device value is an OVERRIDE, drawn as one, kept for a rotation in progress.
That is a decision for the operator (section 9).

## 3. Inheritance and overrides

**Effective intent = the profile's sections for the device's platform and role, overlaid
by the device's own intent.** Where a key is set on both, the device's value wins. One
function computes it (`hostvars.effective(intent, profile, device)`), and every reader of
intent calls it: render, the deploy plan, restore validation, round-trip, seed and the
editor's preview. A second merge would be two answers to "what should this device look
like".

- **An override is visible.** A device value that differs from the profile's is drawn as
  "overrides the profile" in the editor and the plan, never silently.
- **An exclusion carries a reason.** A section the device must not have is excluded with
  `profile_exclude: [{section, reason}]`, committed in its intent, the reason's shape rule
  as for an authorised line. An exclusion without one is refused.
- **One owner, enforced at extraction and seed.** A device-intent value EQUAL to what the
  profile supplies is dropped at seed and at extraction, because the device inherits it.
  So the fleet's hand-written SNMP lines become inherited once the profile holds the same
  values, and a device's intent holds only what is its own. C216's "seed keeps declared
  blocks" is subsumed: the syslog block lives in the profile, so seed has nothing of it to
  drop. Onboarding's own merge of the block into `host_vars` is removed.
- **A profile change is a change to every device's intent.** Its commit's preview names the
  devices whose effective intent moves. Reaching the devices is a fleet deploy (section 5),
  never a side effect of the commit.
- **Template approval is unaffected.** Scheme 3 keys on the templates' closure hash, and
  the profile is data. A device the template cannot reproduce stays blocked alone, by its
  own `template_report`.

## 4. New devices: onboarding's phase 2, and adopt

**Not in the bootstrap** (the operator's three reasons, kept):
- a ZTP bootstrap travels over cleartext TFTP, and the community would travel with it;
- on vIOS the bootstrap is replayed line by line through the console, the path stage D
  exists to measure;
- configuration placed there sits outside intent and the profile.

**Phase 2 applies it, over SSH, in the operation that already holds the device.** The
order becomes: verify, capture, rotate, remove RW, APPLY THE PROFILE, persist, re-read,
first golden, NetBox, promote. The profile's lines land before the first capture, so the
first golden already records monitoring, and the device is monitored the moment
onboarding finishes. The push is the deploy path's merge program on the held session
(`merge_commands`, `assert_sendable`, `assert_merge_only`, `assert_credentials_unchanged`).
It is verified by reading each line back, and undone by the computed rollback on failure,
leaving the device pending with the step named.

**This makes Verify a preview and a confirm** (a decision, section 9). Phase 2 is one click
today (`SELF_CONFIRMED`), because nothing it sent needed reading. A program of profile
lines does: the preview reads the device, as adopt's plan does, draws the profile's lines
grouped as in section 5, and the confirm is bound to their fingerprint. **Adopt** gets the
same step, in its apply, after the tool's account is proven.

## 5. Existing devices: "Apply monitoring profile"

The device's intent already inherits the profile, so nothing is seeded: the device has
simply not received it. **The action is a deploy plan scoped to the profile's lines.** The
plan attributes every line it would send as `from_this_edit`, `pre_existing` or, new,
`from_profile`. This action selects the `from_profile` lines and their ancestors, through
preview, confirm, result, push, verify and rollback, like any deploy. It sits on the device
page's Monitoring section, and on the fleet coverage page for several devices.

**The preview shows three groups:**
- **Inherited from the profile: will be sent.** Each line, with the section and connector
  it comes from.
- **Already in place.** Profile lines the device has, stated so the reader knows they were
  checked.
- **Superseded on the device.** A brownfield device may carry DIFFERENT monitoring
  configuration: an old `logging host`, another community, another `ntp server`. Merge-only
  would add the profile's lines beside them. Each superseded line is named as "superseded
  by the profile", with a box to REMOVE it through Mode B and a reason field for each.
  Nothing is removed unless its box is ticked, and never silently. A line whose shape Mode
  B has not measured on that platform is drawn with its box disabled and the reason beside
  it ("not measured to remove exactly itself on cisco_iosxe"). **Measured already, on both
  platforms: `logging host` and `snmp-server community` remove exactly themselves**
  (`removal_measured.json`; this document first said the community was unmeasured on
  IOS-XE, repeating C139's older note instead of reading the record). **Not yet: `ntp
  server` and `snmp-server host`**, the other lines a device can hold several of. A
  single-value setting (the trap level, the source interface) is REPLACED by the push, so
  it is never superseded beside itself. Both shapes are declared, and refused until the
  operator's probe run (NSOT_STAGE7_PLAN, "Staged runs", 4). None of it blocks r6, which
  has no monitoring configuration to supersede.

**Fleet coverage.** The Monitoring page gains Coverage: devices by integration (SNMP,
syslog, heartbeat, telemetry, IP SLA), each cell from the committed golden
(`monitoring_coverage`, extended to telemetry and IP SLA), with a device's exclusions drawn
as such. Selecting several devices opens ONE batch preview, in the deploy batch's order:
sequential, with the circuit breaker, the order drawn. Needs attention already carries one
row per uncovered device. Its action becomes this one when it exists.

**r6 is the first case.** Once the profile exists, "Apply monitoring profile" on r6 sends
its SNMP lines, and the next target generation makes it a target. r6's intent is NOT
hand-edited before then.

## 6. IP SLA: a policy in the profile, operations in the device's intent

A probe targets another device's address, so addresses are the device's own data. The
profile holds the POLICY:
- `gateway`: probe the device's default route next hop;
- `peers`: probe its routing peers, read from the capture's OSPF neighbours and BGP peers;
- `none`;
- plus `type` (icmp-echo) and `frequency`.

The preview SUGGESTS operations from the device's own facts. The person accepts or edits
them, and they are committed into the DEVICE's intent (`ip_sla`, which the parsers already
model). **Recommended over fixed addresses in the profile**, which would be wrong for every
device but one, and over a pure per-device item, which gives a new device nothing.

**Built (d4's ADD path, 2026-10-01; `modules/nsot/ip_sla_policy.py`, Monitoring > IP SLA at
`/v2/monitoring/ip-sla`).** The operator split adding from changing: adding a probe is a new
operation, merge-only; changing a running one is the re-create (C290), which waits on staged
run 9. What was built, and what differs from the paragraph above:
- `peers` reads the adjacencies the device's COMMITTED INTENT implies (`modules.neighbours`,
  OSPF and BGP), not a capture: one probe per shared network, since on a segment every peer
  measures the same path. RIP's peers are not read, and a RIP device says so ("choose its
  targets by hand"). `gateway` is the static default in the global table only (a VRF's
  default, the emulator's `clab-mgmt`, is never a gateway).
- **The default is every 60 s** (the operator: one probe every 10 s cost s3 about 12% of its
  CPU, C93), `frequency` and `frequency_by_platform` in the section, 10 to 3600.
- **A switch's path to a router is placed ON THE ROUTER**, which probes the switch's
  loopback: the same path, sparing the switch. A path an existing probe measures, from either
  end or on the same segment, is not added again (s3 is skipped: its `ip sla 1` covers
  10.255.3.0/24).
- **Every suggestion states its expected CPU cost**: measured on vIOS only (12% at 10 s,
  scaled by frequency), and "not measured" on IOS-XE.
- The ticked suggestions are ONE intent commit (`Source: ip-sla`, as the person, refused if
  the plan moved, if host_vars/ holds an uncommitted change, or with nothing ticked; a failed
  commit puts every file back), then the batch Apply with scope `ip_sla` sends ONLY the IP SLA
  lines, each device's exact program previewed and confirmed by hash.
- On the real fleet with `peers`: s4 gets `ip sla 2` on r2 probing s4's loopback every 60 s;
  s1 and s2 run RIP (by hand); s3 is already measured.
- After any IP SLA apply to a switch, its CPU and clock rate are read before and after from
  Prometheus (the operator, 2026-10-01).

## 7. What it replaces

- P.1's block written by onboarding. The profile's syslog and heartbeat sections replace
  it.
- C216's "seed keeps declared blocks". Subsumed, since the block is inherited.
- The fleet's hand-written SNMP lines. They become inherited at the next extraction or
  seed, where they equal the profile.
- C235 for the monitoring secrets, through the profile-scoped key.

## 8. Where it lands in the order (proposed)

**Next, before the rest of step 4's tabs:** every new device hits r6's problem until this
exists, and step 4's Monitoring section is where its action lives. Four steps, each with a
host run:

- **(a) The model.** The profile document and its commit path; `hostvars.effective()` and
  every reader moved onto it; the profile-scoped secret; `from_profile` attribution in the
  plan; one owner at seed and extraction. From the real fleet goldens, the acceptance: the
  fleet's current SNMP and syslog lines are inherited, and no device's plan changes.
- **(b) Existing devices.** The scoped deploy with its three groups, and superseded lines
  through Mode B (after the operator's removal probe run). r6 first: its alert clears, and
  it becomes a target.
- **(c) New devices.** Onboarding's phase 2 and adopt apply the profile; Verify becomes a
  preview and a confirm. Acceptance: a throwaway device onboarded, monitored at promotion,
  its first golden holding the profile.
- **(d) The screens, in v2.** The device page's Monitoring section (coverage and the
  action) and the fleet Coverage page, as part of step 4.

It needs P.8 only for the connector settings to be per network. Until then they are the
installation's, which is the one network today.

## 9. Decisions: ALL FIVE AGREED (the operator, 2026-09-30), and P.9 goes next

1. **Verify becomes a preview and a confirm**, because phase 2 now sends a program.
2. **One SNMP community per network**, with a device value as an override. Already true in
   practice: snmp_exporter polls the whole fleet with one auth module. This reverses C139's
   one-value-per-device rule (recorded there, with why). SNMPv3 (Stage 9) is the real fix
   for a community that has been published.
3. **The removal probe run is the operator's**, at the next lab session: `ntp server` and
   `snmp-server host` on both platforms (NSOT_STAGE7_PLAN, "Staged runs", 4). It does not
   block r6.
4. **Two new per-network settings: the Telegraf endpoint and the NTP servers.** A benefit
   the operator named: NTP in the profile corrects the switches' clocks, which run slow and
   have drifted by days (C9: s3's heartbeat stamped Sep 26 on Sep 29).
5. **IP SLA as a policy** in the profile (the gateway, the routing peers, or nothing), with
   the suggested addresses committed into each device's own intent, where they are
   reviewed.

Built in the four steps of section 8: the model; existing devices, r6 first ("Apply
monitoring profile" clears its warning); onboarding and adopt; then its screens inside the
redesign's step 4.

## 10. The management section (the operator, 2026-10-07; Phase 2's P1)

Management protocols leave from the management interface, through intent: a section of this
document, `management`, beside the monitoring ones, rather than a second document (the
profile's reader, merge, Propose, Apply and screens all take a section as it comes, and a
second document would duplicate each). It holds `source_interfaces: {tftp, ssh}` (`ip tftp
source-interface`, `ip ssh source-interface`; later `ip scp server enable`, C562), a scalar
each, so a device's own value overrides it key by key. Carried in the `ssh` list, as the
parser held `ip ssh source-interface` before, a device's own list replaced the profile's
whole list and the line was lost.

- **Derived, not declared again:** from `syslog_source_interface`, the interface syslog and SNMP
  traps already leave from, and only where `syslog_host` is configured: the setting has a
  default (`Loopback0`), and a network that never configured syslog never chose it.
- **Why it exists:** M1 (2026-10-07) measured TFTP leaving r2 and s1 from data interfaces,
  while Mercury knows each by its loopback; Phase 2's one-shot transfer is served to that
  address only ([NSOT_REVERT_BY_RELOAD](NSOT_REVERT_BY_RELOAD.md), 9b).
- **Verify:** quick. The lines change what the device sends from, never what it routes or how
  Mercury reaches it (`verify_scope.MANAGEMENT`, "management sources").
- **Known wording:** Monitoring › Apply still calls the whole document "the monitoring profile";
  its preview names the section ("From the profile's management sources section").
