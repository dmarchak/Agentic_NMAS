# IPv6 parity: audit and design

The operator's decision, 2026-10-17: "Mercury must support IPv6 equally.
Every feature works on an IPv6-only management network: adding devices
(static and ZTP), SSH, deploy/verify/rollback, adopt, monitoring, silences,
logs, path trace, rotation, DHCP and NetBox." Charter bucket: **FUTURE**, the
first epic of Phase 8. This document is the read-only audit (section 1 to 4),
the designs (5 to 7), the measurement plan (8) and the register shape (9).
Written 2026-10-17 against `00871987`. Nothing here was run on a host, a
device, NetBox, Kea or Grafana.

## The standing rule (the operator, 2026-10-18; the Core 1.0 triage)

- **The 109 break sites found below stay a post-1.0 epic** (C1245), done before Stage 10's
  release gate. They are not part of Core 1.0.
- **From now on, every Core capability that handles addresses is built and tested to work on
  an IPv6 management address as well as IPv4.** "Handles addresses" covers parsing,
  formatting, validating, comparing, storing, connecting to or serving one.
- **The tests:** each such capability's tests carry an IPv6 case beside the IPv4 one, through
  the same path, using documentation addresses: 2001:db8::/32 beside 192.0.2.x.
- **A path that cannot be tested for IPv6 without a live network** (a device's answer, a TFTP
  transfer) is tested on a captured or planted IPv6 answer, and walked on the host when the
  lab has an IPv6 management address (section 8).
- **A capability that cannot serve IPv6** (ZTP, which is DHCPv4 today, section 5) says so on
  its screen and in its manual page, by name. It never fails silently on an IPv6 address.
- **No break site may be added.** A new site listed in section 4's form is a defect in the
  capability that added it, not a new entry for the epic.
- **The cost is in each item's size** (docs/COMPLETION_INVENTORY.md section 6). None moved to a
  larger size.
- **Enforced:** CLAUDE.md's IPv6 line, as the operator pastes it; each capability's own tests;
  and the review of every Core commit. Not mechanised as a scan yet.

## 1. Counts

**371 address-handling sites: 109 break, 9 unknown, 253 work** on an
IPv6-only management network. 52 verdicts were settled by an in-process
check (a pure function called with an IPv6 literal). The other 319 were
read from the code and are marked READ.

| Plane | Breaks | Unknown | Works |
|---|---|---|---|
| M, the management path (how Mercury reaches, identifies and records a device) | 66 | 6 | 167 |
| D, device content (addresses in configs, show output and intent) | 28 | 3 | 61 |
| H, Mercury's own host and services | 15 | 0 | 25 |

**How the population was found.** A property scan (a working script of the
audit, not committed) ran over 659 tracked product
files, excluding `tests/`, `docs/` and vendored code. It matched 13 property
classes:
- dotted-quad regexes, `ipaddress`, masks and prefix lengths;
- `host:port` and `split(":")`;
- Kea keywords, PromQL and LogQL label matchers, and SNMP targets;
- SSH and known_hosts, URLs with an address, and NetBox IPAM;
- intent and template address fields, socket families, and fields named like an address.

The scan hit 2,348 lines in 283 files, which fall into 1,003 candidate
function-level sites. Each candidate was read and judged. 1,212 hit lines
turned out not to handle an address: the word "host" meaning a hostname,
`job=` ids, list-of-dict literals, vendored Bootstrap, and prose. A function
that only passes an address through unparsed is listed as a carrier ("works:
opaque carrier") when it is on a feature path.

**The scan's floor and its planted case.**
- **Floor:** 300 sites. The scan's own Kea, NetBox and SSH classes reach
  that many on the files already named in the operator's list.
- **Planted case:** the scan ran with a planted
  `IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")` and found it.
- **Misses:** a second, looser sweep found one IPv4 pattern the
  dotted-quad class missed: `modules/goldens.py:42`, an underscored
  `\d+_\d+_\d+_\d+\.cfg` in a legacy migration that does not matter for
  IPv6. The reviewers found **19 more sites the scan missed** and marked
  each one "(MISSED BY SCAN)" in the table. Examples:
  - `path_trace.py`'s `show ip cef` command and its `via [0-9.]+` regex;
  - `_upsert_device`'s IPv4-only management-address match;
  - the `logging host` parser and template (IOS writes `logging host ipv6 <addr>`);
  - `pkt4.giaddr` in the ZTP class test.
- **Measured miss rate:** about 5% of the final population. A future scan
  should add `via\s+\(\[0-9\.\]`, `show ip `-family command literals and
  `pkt4`.

**The one cross-cutting defect: addresses compared as text.** IOS prints
IPv6 in upper case (`2001:DB8::10`) in running-config and show output.
NetBox, Kea and Python's `ipaddress` print lower case. Operators type
either, and also uncompressed forms. The inventory stores the address as
typed (`modules/device.py:237`). About 40 sites compare addresses with `==`
on strings, and they work only while every source spells the address the
same way. The ZTP responder (`ztp_responder.py:127`), adopt's duplicate
check (`adopt.py:843`, `manifest.find_by_ip`), Kea conflicts
(`ztp.py:669`, `dhcp_reservations.py:487`), verify's read-back
(`verify_scope.py:108`) and the host-key, credential and alert joins break
on a second spelling. IPv4 never had this problem. **One rule closes the
class:** canonicalise at entry (RFC 5952, `ipaddress.ip_address(x).compressed`)
and compare parsed objects wherever a device's own text is involved.

## 2. The top breaks

1. **ZTP is IPv4 from end to end.** `modules/nsot/ztp.py` reads only `Dhcp4`
   and `subnet4` (`:89`, `:98`, `:131`). It writes DHCPv4 options 66 and 67
   (`:394`), finds host addresses with AF_INET only (`:189`, `:325`) and
   probes broadcast DNS over AF_INET (`:222`). `posture` (`:281`) therefore
   refuses every IPv6 ZTP plan.
2. **The ZTP responder's systemd sandbox** (`deploy/systemd/nmas-ztp-responder.service:25`,
   `RestrictAddressFamilies=AF_INET AF_UNIX`) blocks the AF_INET6 reply
   socket that `normalise_peer` already chooses for a real IPv6 peer. The
   device would hear silence, which is M4b's failure in the other family.
3. **The static bootstrap renders `ip address A M` and
   `ip route 0.0.0.0 0.0.0.0 gw` only** (`bootstrap_config.py:280,304`).
   An IPv6 address becomes `ip address 2001:db8::5 64`, which IOS rejects
   at boot. The plan validates nothing (`onboard.py:726`, `:277`), so
   nothing refuses it earlier.
4. **NetBox never makes the management address `primary_ip6`.**
   `netbox_client.py:2433,2656,2694` (and tier 3 builds `ip/32` for a v6
   address). `inventory/netbox_source.py:130` reads `primary_ip4` only, so
   an IPv6-only device in a NetBox-sourced list is skipped. The NetBox tab
   draws "Primary IPv4" only (`device_netbox.py:109`, `_netbox.html:28`).
5. **Deploy's diff treats `ipv6 address` as one setting.** IOS adds a new
   IPv6 address beside the old one. `deploy.py:781` gives every
   `ipv6 address` the same key, so `classify_diff` calls a new address a
   replacement (`:212`), and rollback re-sends the old line instead of
   `no ipv6 address <new>` (`:1050`). The added address survives rollback.
6. **Verify's read-back compares text** (`verify_scope.py:108`), and IOS
   upper-cases IPv6. A correctly landed `ipv6 address` or `ipv6 route`
   reads as "did not land", and the change is rolled back. Route retention
   reads `show ip route summary` only (`pipeline.py:2514`).
7. **Path trace is IPv4 only, and says so.** It uses `show ip cef` alone,
   a `via [0-9.]+` regex, `IPv4Address` and `_PREFIX`, `owners` and
   `destinations` drop every `:` address, and `refusal` refuses version 6
   by name (`path_trace.py:32-422`).
8. **Mode B does not protect an IPv6 management interface.**
   `removal.py:386` recognises only `ip address <mgmt>`. `privileged.py:142`
   and `blast_radius.py:42,127` share the IPv4-only management view, so
   every reload's blast radius reads "unknown" on an IPv6-only host.
9. **Silences and acknowledgements miss IPv6 instances.**
   `restarts.py:270`'s matcher misses `[2001:db8::1]:port`.
   `acknowledgements.py:106` strips the port at the first colon, which
   turns the address into "2001".
10. **Kea's device-onboarding reads are DHCPv4 only.**
    `kea.reservation_for` and `lease_for` use hw-address, dhcp4 and lease4
    (`kea.py:192,258,318`). `dhcp_discovery.py` (AF_INET, `pkt4`, option 60,
    `/27` arithmetic) and `readers/ztp_discovery.py` are DHCPv4 only too,
    so a DHCPv6 device never appears in Discovered. **The DHCP page itself
    is family-aware:** subnet6, lease6 and DUID reservations all work.

Also: the online check and reachability use `ping3`, which is AF_INET only
(`connection.py:779`, `readers/reachability.py:78`). Over IPv6 only the
TCP:22 fallback answers, so a device with SSH closed reads as offline.
`logging host` is parsed and rendered without IOS's `ipv6` keyword
(`parsers/base.py:544`, `_common.j2:201`). `ip_sla_policy.py` derives
IPv4 targets only.

**What already works.** SSH and NETCONF transports work: Netmiko and
Paramiko, and ncclient, resolve with `getaddrinfo(AF_UNSPEC)`. Mercury's
host-key store is keyed by address string, not known_hosts text. Device
logs are selected by hostname or the `device` label, never by source
address, and rsyslog's imudp listens on both families. The parsers, intent
and templates handle `ipv6 address`, `ipv6 route`, OSPFv3 and RIPng.
Topology, neighbours and BGP summary are family-aware. The DHCP editors
work in both families, and so does the confined test namespace (`::1`
CHECKED).

## 3. Per feature: what breaks and the smallest change that makes it work

| Feature | Sites (break / unknown / work) | What breaks | Smallest set of changes |
|---|---|---|---|
| Adding a device, static | 8 / 0 / 30 | No address validation. A separate dotted "Mask" field. The bootstrap renders only `ip address A M` and an IPv4 default. The diagnosis tells the operator to read `show ip interface brief`. The online check's ICMP is IPv4 only | Parse `address/prefix` with `ip_interface` in `onboard.build_plan`, refusing a mixed family and naming both operands. The form takes a prefix length (section 6). `manager_interface_lines` renders `ipv6 address A/len` and `ipv6 route ::/0 gw` by family. Canonicalise `mgmt_ip` at entry. A family-aware ICMP probe |
| Adding a device, ZTP | 36 / 1 / 15 | Everything in `ztp.py`, the Kea reads, the discovery range and reader, the responder's systemd family line, D4's option list | Design A in section 5: a Dhcp6 path beside Dhcp4 in `ztp.py`, with a subnet6 include fragment, option 59 in place of 66 and 67, `kea-dhcp6 -t`, lease6 reads, and an AF_INET6 server address. D4's IPv6 conditions (option 23, RAs). `AF_INET6` in the unit. Discovery by DUID or derived MAC. All of it waits on M6-1 to M6-4 |
| SSH | 0 / 0 / 9 | Nothing in code | The canonical form, so the host-key and credential joins hold |
| Deploy, verify, rollback | 12 / 0 / 24 | `ipv6 address` treated as one setting (diff, rollback). Text read-back. Route retention and EIGRP for IPv4 only. Expected effects and blast radius use IPv4 attachments. Mode B's management interface is IPv4 only | Key `ipv6 address` by the full line (additive), and roll back with `no ipv6 address <added>`. Compare read-back by parsed address. Add `show ipv6 route summary` to retention. Add IPv6 attachments to `expected_effects`, `blast_radius` and `removal._management_interfaces` |
| Adopt | 2 / 0 / 10 | Duplicate checks by text (`adopt._plan`, `manifest.find_by_ip`) | The canonical form at entry and in `find_by_ip` |
| Monitoring | 11 / 2 / 19 | ping3 is AF_INET only. Drained reads `ip address` only. The connector tests (`sntp_answers` AF_INET, `tcp_accepts` brackets). IP SLA targets are IPv4 only. The `telemetry_receiver` split. Whether snmp_exporter accepts a bare IPv6 target is UNKNOWN | Probe ICMP by family. Read `ipv6 address` in Drained. Parse `[addr]:port` in one shared helper. Write file_sd targets as `[addr]` (or `udp6:[addr]`) once M6-7 measures the form. IP SLA from IPv6 addresses and OSPFv3 peers |
| Silences | 2 / 0 / 2 | `restarts._matchers` misses `[v6]:port`. `acknowledgements.devices_of` splits at the first colon | Match `\[?addr\]?(:port)?`, and the shared host:port parser |
| Logs | 3 / 2 / 5 | `logging host ipv6` parsed and rendered wrongly. The trap `device` label for a v6 source is UNKNOWN | Parse and render `logging host ipv6 <addr>`. One trap from an IPv6 source (M6-7) |
| Path trace | 7 / 0 / 1 | All of it | `show ipv6 cef <dest>` (or `show ipv6 route`), a parser for its next-hop lines, link-local next hops attributed through the interface, and `owners` and `destinations` keeping IPv6 |
| Rotation | 1 / 1 / 10 | The yang-push consumer's dotted-quad `HOST` regex (a retired consumer) | `ip_address` over the quoted value |
| DHCP | 7 / 0 / 36 | Text comparisons in reservations. `span()` refuses prefix-form pools. The one-off Kea host-step tools need dhcp4 to answer. `bootstrap`'s `ip address dhcp` has no IPv6 form | Compare parsed addresses. `span()` takes prefixes. The tools treat a missing family as absent, not as an error. `ipv6 address dhcp` |
| NetBox | 7 / 0 / 23 | `primary_ip6` is never the management address. The inventory reads `primary_ip4` only. The tab draws IPv4 only. `ipv6 route` is never read. The device-content parsers that are still called are fine (three dead parsers are IPv4 only) | One resolver: the management address of either family becomes `primary_ip4` or `primary_ip6`. Read either in `netbox_source`. Draw both. Parse `ipv6 route` |
| Topology | 2 / 1 / 13 | The CDP and LLDP IPv6 neighbour address is lost, and nothing reads it today. The cbgpPeer2 label form is UNKNOWN | The regexes take IPv6. One IPv6 peer's label read (M6-7) |
| Other (host, scripts, reads) | 11 / 2 / 56 | The trusted-peer comparison by text (`identity.py:287`). The bind default `0.0.0.0` and the printed URL. The `reads.py` common commands are IPv4 only. The hand-run responder's `--listen`. MinIO and Loki host-step bracket handling. Two lab probes. The retired Oxidized helper | Compare the trusted peer by `ip_address`, and unmap `::ffff:`. Offer IPv6 reads. The shared host:port helper |

## 4. The site table

Every site, grouped by feature, breaks first. `file:line` is the decisive
construct. Plane is M, D or H as in section 1. "How" says whether the
verdict was CHECKED in process or READ from the code.

#### static-onboard (38 sites: 8 break, 0 unknown, 30 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/connection.py:779` | `is_device_online` | M | BREAKS | READ | ping3 4.0.4 is AF_INET only (socket.gethostbyname raises, ping returns False), so the ICMP half never answers for IPv6; the TCP:22 fallback (create_connection) does, so only an SSH-closed but pingable device reads offline. |
| `modules/nsot/bootstrap_config.py:280` | `manager_interface_lines` | M | BREAKS | READ | Renders only `f" ip address {address} {mask}"` (also line 296); an IPv6 address with prefix 64 becomes `ip address 2001:db8::5 64`, which IOS rejects at boot; no `ipv6 address A/len`/`ipv6 enable` form and no family check. |
| `modules/nsot/bootstrap_config.py:304` | `manager_interface_lines` | M | BREAKS | READ | `f"ip route 0.0.0.0 0.0.0.0 {gateway}"` is the only gateway form; an IPv6 gateway renders an invalid IPv4 route, and `ipv6 route ::/0 <gw>` is never emitted. |
| `modules/nsot/bootstrap_config.py:471` | `render_bootstrap` | M | BREAKS | READ | A vIOS's own management port gets only ` ip address dhcp`; an environment whose management network is IPv6-only leaves that port unaddressed (low weight: it is the emulator's own network). |
| `modules/nsot/onboard.py:2490` | `_causes` | M | BREAKS | READ | The diagnosis tells the operator to run `show ip interface brief`, which lists no IPv6 addresses (`show ipv6 interface brief` does); the suggested `ping {mgmt_ip}` works with iputils. |
| `modules/nsot/onboard.py:277` | `blocking_reasons` | M | BREAKS | READ | Checks only presence of a "network mask" (message: "a /24 assumption"); there is no prefix-length concept or family check, so an IPv6 plan passes every reason and is not refused. |
| `modules/nsot/onboard.py:726` | `build_plan` | M | BREAKS | READ | Nothing validates mgmt_ip, mgmt_mask or manager_gateway (no ipaddress anywhere in onboard.py); an IPv6 address is accepted and passed to render_bootstrap, which emits `ip address` — refused only by the device, after boot. |
| `templates/v2/_onboard_add.html:62` | `<template>` | M | BREAKS | READ | The static form has a separate "Mask" field (placeholder 255.255.255.0) and no prefix-length field: an IPv6 address has no dotted mask to type. Validation is in modules/nsot/onboard.py (judged in its `modules/nsot/` row). |
| `modules/credentials.py:547` | `resolve/_from_credential_list` | M | works | READ | device overrides and the designated credential list are keyed/compared by the exact mgmt address string; works for IPv6 given one spelling. |
| `modules/device.py:237` | `save_device/delete_device` | M | works | READ | rows matched by exact `row.get("ip") == device.get("ip")`; no parse, so IPv6 is stored and matched as typed (not canonicalised). |
| `modules/device_list.py:516` | `listing` | M | works | READ | address shown and searched as a lowercase substring; no parsing. |
| `modules/inventory/__init__.py:106` | `_rehydrate` | M | works | READ | Opaque carrier: dev["ip"] passed to credential resolution as a string. |
| `modules/inventory/__init__.py:357` | `_record_stale_devices` | M | works | READ | Opaque text keys; a v6 address respelled (case or compression) between loads would read as one stale and one new device. |
| `modules/nsot/bootstrap_config.py:439` | `render_bootstrap` | M | works | READ | `ip domain name`/`ip domain-name`, `crypto key generate rsa`, `ip ssh version 2` and `transport input ssh` are address-family neutral; IOS SSH serves IPv6 once an IPv6 address exists. |
| `modules/nsot/manifest.py:170` | `upsert_device` | M | works | READ | Stores mgmt_ip and mgmt_prefix_len opaquely. |
| `modules/nsot/manifest.py:589` | `_credential_findable` | M | works | READ | Opaque key to credentials. |
| `modules/nsot/onboard.py:1088` | `pending_bootstrap_staged` | M | works | READ | Opaque credential keys mgmt_ip and reserved_address passed to credentials.resolve. |
| `modules/nsot/onboard.py:1451` | `bind_credentials_step` | M | works | READ | Credential override keyed on the same mgmt_ip string verify later resolves (static); for ZTP the key is the typed reservation, matched against the lease (see discover_dhcp_address). |
| `modules/nsot/onboard.py:1626` | `commit_step` | M | works | READ | Opaque carrier of plan.mgmt_ip into adopt_identity, the manifest and committed bootstrap parameters. |
| `modules/nsot/onboard.py:1829` | `record_run` | M | works | READ | Records mgmt_ip as an opaque string. |
| `modules/nsot/onboard.py:2164` | `_abandon_onboarding` | M | works | READ | Opaque keys to credentials.clear and host_keys.forget_plan/forget for mgmt_ip and reserved_address. |
| `modules/nsot/onboard.py:2357` | `promote_device` | M | works | READ | Opaque carrier of the manifest mgmt_ip into the inventory row. |
| `modules/nsot/onboard.py:2702` | `verify_device` | M | works | READ | Opaque carrier of mgmt_ip to connection.is_device_online / verify_device_connection (another group's sites). |
| `modules/nsot/onboard.py:3012` | `capture_config` | M | works | READ | Opaque carrier: {"ip": mgmt_ip} to the connection layer. |
| `modules/nsot/onboard.py:3096` | `phase_two_plan` | M | works | READ | Opaque carrier of the verified mgmt_ip to capture and credentials.resolve. |
| `modules/nsot/onboard.py:3136` | `send_profile_program` | M | works | READ | Opaque carrier: {"ip": mgmt_ip} to the connection layer. |
| `modules/nsot/onboard.py:3188` | `persist_on_device` | M | works | READ | Opaque carrier: {"ip": mgmt_ip} to the connection layer. |
| `modules/nsot/onboard.py:3252` | `check_startup` | M | works | READ | Opaque carrier: {"ip": mgmt_ip} to the connection layer. |
| `modules/nsot/onboard.py:3315` | `remove_rw_communities` | M | works | READ | Opaque carrier: {"ip": mgmt_ip} to the connection layer. |
| `modules/nsot/onboard.py:3472` | `run_phase_two` | M | works | READ | Opaque carrier of mgmt_ip and the lease prefix length to the manifest, inventory row and device steps. |
| `modules/nsot/onboard.py:3485` | `_cred` | M | works | READ | Opaque key to credentials.resolve. |
| `modules/nsot/onboard.py:3783` | `_save_first_golden` | M | works | READ | Opaque carrier into GoldenItem/save_golden. |
| `modules/nsot/onboard.py:484` | `address_claim` | M | works | READ | Display only: f"{mgmt_ip} {mgmt_mask}" shows "2001:db8::5 64", odd but not wrong. |
| `modules/nsot/onboard.py:75` | `OnboardPlan` | M | works | READ | Stores mgmt_ip/mgmt_mask/manager_gateway/reservation_address as opaque strings; no parsing. |
| `modules/preview_confirm.py:1068` | `onboard_preview/onboard_verify_preview/onboard_create_result/onboard_verify_result/retire_preview/persist_preview/rekey_preview/rotate_preview/breakglass_preview/expected_part` | M | works | READ | display carriers of plan mgmt_ip/ip (onboard renders "A M" only when the plan carries a mask); correctness of the plan's values belongs to nsot/onboard. |
| `routes/onboard.py:124` | `_plan_args` | M | works | READ | Opaque carrier of mgmt_ip to onboard.plan (judged in its `modules/nsot/` row). |
| `routes/onboard_v2.py:30` | `<file>` | M | works | READ | FIELDS carries mgmt_ip, mgmt_mask, manager_gateway as strings to onboard.plan (judged in its `modules/nsot/` row): opaque carrier. |
| `templates/v2/_onboard_add.html:60` | `<template>` | M | works | READ | The address input is free text with no pattern attribute; acceptance is decided server-side (judged in its `modules/nsot/` row). |

#### ztp (52 sites: 36 break, 1 unknown, 15 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `deploy/systemd/nmas-ztp-responder.service:25` | `<unit>` | H | BREAKS | READ | RestrictAddressFamilies=AF_INET AF_UNIX: the TFTP reply goes from a NEW socket of the peer's family (ztp_responder.py:260); for a real IPv6 peer socket(AF_INET6) is refused by systemd's filter, so the device hears silence. |
| `modules/dhcp_discovery.py:117` | `classes_plan` | M | BREAKS | READ | Inserts the classes before the "subnet4" key of the dhcp4 file only. |
| `modules/dhcp_discovery.py:136` | `pools` | M | BREAKS | CHECKED | `net.version != 4` refuses any IPv6 block ("is not an IPv4 block of 32 addresses"). |
| `modules/dhcp_discovery.py:147` | `_taken` | M | BREAKS | READ | Reads IPv4 reservations and intent["IPv4"] only. |
| `modules/dhcp_discovery.py:180` | `free_range` | M | BREAKS | CHECKED | subnets(new_prefix=32 - 5) hard-codes the IPv4 width; on a v6 subnet it raises ValueError "new prefix must be longer". |
| `modules/dhcp_discovery.py:225` | `running` | M | BREAKS | READ | Reads the ZTP subnet from dhcp4's subnet4 only. |
| `modules/dhcp_discovery.py:244` | `plan` | M | BREAKS | READ | Family "IPv4" hard-coded; kea_leases(kea, "IPv4") only. |
| `modules/dhcp_discovery.py:57` | `host_addrs` | M | BREAKS | READ | psutil addresses filtered to socket.AF_INET, so a host with only IPv6 on the ZTP segment has no address for ztp.ztp_subnets. |
| `modules/dhcp_discovery.py:68` | `segment` | M | BREAKS | READ | ZTP segment found only in the dhcp4 configuration from IPv4 host addresses; there is no IPv6 ZTP segment. |
| `modules/dhcp_discovery.py:85` | `confined` | M | BREAKS | READ | (MISSED BY SCAN) Class test `pkt4.giaddr == 0.0.0.0` and classes()'s option[60] vendor class are DHCPv4-only expressions; no DHCPv6 (option 16, pkt6) form exists. |
| `modules/integrations/kea.py:192` | `reservation_for` | M | BREAKS | READ | Matches hw-address only and _reservations_from_config reads Dhcp4/subnet4 only; a DUID-keyed DHCPv6 reservation is never found, so onboarding/ZTP reads NOT_RESERVED. |
| `modules/integrations/kea.py:258` | `lease_for` | M | BREAKS | READ | lease4-get-by-hw-address / lease4-get-all to dhcp4 only, matched on hw-address; a device addressed by DHCPv6 (lease6, DUID) is "none". |
| `modules/integrations/kea.py:318` | `_prefix_for_subnet` | M | BREAKS | READ | Reads Dhcp4/subnet4 only, so a lease in a v6 subnet gets prefix length 0 (NetBox falls back to a host route). |
| `modules/nsot/ztp.py:131` | `reservations` | M | BREAKS | READ | Reads Dhcp4 subnet/global reservations keyed by `hw-address` only; DHCPv6 reservations (subnet6, normally keyed by duid) are invisible, so conflicts and the read-back cannot see them. |
| `modules/nsot/ztp.py:158` | `forbidden_options` | M | BREAKS | READ | D4's list is DHCPv4 names/codes (routers 3, domain-name-servers 6, 33, 121); the DHCPv6 resolver option (dns-servers, 23) and RA-supplied routes/RDNSS are never checked, so IPv6 D4 is unguarded. |
| `modules/nsot/ztp.py:189` | `server_address` | M | BREAKS | CHECKED | Host addresses filtered to `a.family == socket.AF_INET`; on an IPv6-only host it refuses "found 0" (with addrs injected, 2001:db8::5 in 2001:db8::/64 is returned correctly). |
| `modules/nsot/ztp.py:222` | `dns_answerers` | M | BREAKS | READ | `socket.AF_INET` + SO_BROADCAST + sendto("255.255.255.255", 53) bound to the host's segment address; an IPv6 source cannot bind an AF_INET socket, the probe errors to "unknown", and posture refuses every IPv6 plan. |
| `modules/nsot/ztp.py:281` | `posture` | M | BREAKS | READ | Chains _dhcp4 → subnet_for_address → server_address → dns_posture; for an IPv6 reservation address each step refuses, so plan_check refuses every IPv6 ZTP onboarding. |
| `modules/nsot/ztp.py:325` | `ztp_subnets` | M | BREAKS | READ | AF_INET-only host addresses matched against Dhcp4 `interfaces-config`; on an IPv6-only host posture_rows reports "no Kea subnet holds this host's address" forever. |
| `modules/nsot/ztp.py:394` | `reservation_entry` | M | BREAKS | READ | Writes DHCPv4 options `tftp-server-name` (66, SERVER_OPTION line 66) and `boot-file-name` (67); DHCPv6 has neither: IOS-XE IPv6 autoinstall needs option 59 bootfile-url (tftp://[addr]/file), which nothing builds. |
| `modules/nsot/ztp.py:445` | `_config_test` | M | BREAKS | READ | Calls run(test_main) whose default is _run_kea_test(program="kea-dhcp4"); a Dhcp6 candidate would be tested by the IPv4 server binary and refused. |
| `modules/nsot/ztp.py:529` | `write_reservations` | M | BREAKS | READ | Main config defaults to kea-dhcp4.conf and _includer asks dhcp_subnets.move_plan(..., "IPv4"); there is no IPv6 fragment, main config or include path for a ZTP reservation. |
| `modules/nsot/ztp.py:571` | `_write_reservations_locked` | M | BREAKS | READ | Reads Dhcp4, lease4 leases and reads back reservations(Dhcp4); an IPv6 entry is refused by forbidden_options → subnet_for_address (no subnet4 holds it), so nothing is ever written. |
| `modules/nsot/ztp.py:669` | `conflicts` | M | BREAKS | READ | (spelling) `ip == address` and `leased.get(address)` compare the operator-typed address as text with Kea's canonical strings; an upper-case or uncompressed IPv6 spelling misses a real conflict. |
| `modules/nsot/ztp.py:682` | `_leases` | M | BREAKS | READ | `lease4-get-all` on service `dhcp4` only; IPv6 leases (lease6-get-all, dhcp6) are never read, so a held IPv6 address is never a conflict. |
| `modules/nsot/ztp.py:769` | `progress` | M | BREAKS | READ | (spelling) `r.get("address") == want` and `_peer_host(peer) == want` compare the typed reserved_address with Kea's and Python's canonical forms; a non-canonical IPv6 entry reads "differs" and never matches its fetch. |
| `modules/nsot/ztp.py:89` | `_dhcp4` | M | BREAKS | READ | Reads only `arguments.Dhcp4` of config-get and refuses otherwise; Dhcp6 is never looked at, so no ZTP reservation path exists for an IPv6 management segment. |
| `modules/nsot/ztp.py:98` | `_all_subnets` | M | BREAKS | READ | Enumerates only `subnet4` (top level and shared networks); a `subnet6` holding the device's IPv6 address is never seen, so subnet_for_address finds 0 subnets and refuses. |
| `modules/nsot/ztp_responder.py:127` | `decide` | M | BREAKS | READ | (spelling) `e.get("ip-address") == peer` and `reserved_address == peer`: peer is Python's canonical lowercase form, the fragment and manifest hold the operator-typed text, so an upper-case IPv6 reservation is refused as "holds no reservation". |
| `modules/readers/dhcp.py:296` | `read_family` | M | BREAKS | READ | ZTP subnets measured only `if svc == "dhcp4"`; a v6 subnet is never marked ZTP's. |
| `modules/readers/ztp_discovery.py:149` | `read` | M | BREAKS | READ | kea_config/kea_leases(kea, "IPv4") only: the Discovered list reads dhcp4 alone. |
| `modules/readers/ztp_discovery.py:76` | `shape` | M | BREAKS | READ | Reserved devices from IPv4 reservations with key hw-address only, leases keyed by hw-address; DHCPv6 clients (DUID) can never appear. |
| `scripts/host-steps/ztp-discovery-range.sh:43` | `<file>` | H | BREAKS | READ | Checks, copies and installs kea-dhcp4.conf only (inherits dhcp_discovery's IPv4-only design). |
| `scripts/nmas-kea-discovery-range:57` | `expected` | H | BREAKS | READ | Discovery range tool is dhcp4-only (subnet4, config-reload dhcp4, kea-dhcp4 -t). |
| `scripts/nmas-ztp-responder:54` | `main` | H | BREAKS | READ | The hand-run path parses --listen with rpartition(":") and binds an AF_INET socket: "[2001:db8::10]:69" keeps the brackets in host and AF_INET cannot bind it. Probe and test path only; systemd's path is above. |
| `templates/v2/_onboard_discovered.html:48` | `<template>` | M | BREAKS | READ | ZTP discovery searches by MAC, client-id or hostname and its note is the measured DHCPv4 vendor class (option 60): there is no DUID column, so an IPv6-only device asking DHCPv6 would not appear here. Depends on `modules/readers/ztp_discovery.py` (its own row). |
| `modules/nsot/normalize.py:388` | `_autoinstall_client_id` | D | unknown | READ | Strips only DHCPv4 AutoInstall's `ip dhcp client client-id ascii cisco-…`; what IOS-XE writes after IPv6 (DHCPv6) autoinstall is unknown: capture an IPv6-ZTP'd IOS-XE device's running config and diff it with its rendered intent. |
| `deploy/systemd/nmas-ztp-responder.socket:10` | `<unit>` | H | works | READ | ListenDatagram=69 with no address is a dual-stack [::]:69 socket (measured M4b, docs/P6_ZTP_PROBE.md), bound to the interface by name, not an address. |
| `modules/dhcp_discovery.py:191` | `check_range` | M | works | READ | ip_network/subnet_of of either family; reached only from the IPv4-only plan. |
| `modules/nsot/manifest.py:627` | `pending_devices` | M | works | READ | Opaque carrier of mgmt_ip. |
| `modules/nsot/onboard.py:1736` | `reserve_step` | M | works | READ | Opaque carrier to ztp.write_reservations (breaks there). |
| `modules/nsot/onboard.py:2915` | `bootstrap_artifact` | M | works | READ | Opaque carrier of committed address/mask/gateway into render_bootstrap (breaks there for IPv6). |
| `modules/nsot/ztp.py:108` | `subnet_for_address` | M | works | CHECKED | ipaddress.ip_address/ip_network of either family; given a subnet list containing 2001:db8::/64 it returns it for 2001:db8::5 (it is only ever fed subnet4 by _all_subnets). |
| `modules/nsot/ztp.py:204` | `_dns_query` | M | works | CHECKED | Encodes the fixed probe name nmas-ztp-probe.invalid as DNS labels (split on "." of a NAME, not an address); any reply counts, so the A qtype does not matter. |
| `modules/nsot/ztp.py:744` | `_peer_host` | M | works | CHECKED | ipaddress.ip_address after stripping %zone and unmapping v4-mapped: fe80::1%Gi1 → fe80::1, 2001:DB8::0001 → 2001:db8::1. |
| `modules/nsot/ztp_responder.py:227` | `normalise_peer` | M | works | CHECKED | Native IPv6 peer → (host, (host, port, 0, scope_id), AF_INET6); ::ffff:192.0.2.5 → IPv4/AF_INET; link-local keeps "%eth0" in host and its scope_id in the reply tuple. |
| `modules/nsot/ztp_responder.py:266` | `_handle` | M | works | READ | Reply socket is created in the peer's family and bound to (asked, 0), which AF_INET6 accepts; edge: a link-local asked address comes back without its scope, so that bind would fail. |
| `modules/nsot/ztp_responder.py:320` | `asked_address` | M | works | READ | Parses in6_pktinfo's first 16 bytes with ipaddress (IPv6, v4-mapped unmapped); ask_for_destination sets IPV6_RECVPKTINFO on the dual-stack listener. |
| `modules/nsot/ztp_responder.py:338` | `reply_address` | M | works | CHECKED | Returns the asked address when its family matches the reply socket's ("2001:db8::5" for AF_INET6), else "" (routed choice). |
| `modules/readers/onboarding_progress.py:111` | `judge/address` | M | works | READ | opaque carrier of reserved_address/mgmt_ip to reachability.probe (inherits that probe's ICMP gap). |
| `scripts/nmas-tftp-once:66` | `main` | H | works | READ | AF_INET6 with IPV6_V6ONLY=0 bound to "::": both families. |
| `templates/v2/_pending_progress.html:49` | `<template>` | M | works | READ | Draws mgmt_mac or mgmt_ip as text: opaque. |

#### ssh (9 sites: 0 break, 0 unknown, 9 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/connection.py:177` | `connection_params/stored_connection_params` | M | works | READ | `"ip": dev["ip"]` passed opaque to Netmiko, which sets self.host and calls paramiko connect(hostname=...), resolved with getaddrinfo(AF_UNSPEC): an IPv6 literal connects. |
| `modules/connection.py:383` | `_slot_dir` | M | works | READ | (MISSED BY SCAN) re.sub(r"[^0-9A-Za-z_.-]", "_", ip) turns 2001:db8::1 into 2001_db8__1; injective because no address contains "_", so slots stay per device. |
| `modules/connection.py:448` | `_pin_host_key` | M | works | READ | host_keys.policy(ip, owner, port) closes over Mercury's own ip string and ignores paramiko's hostname argument, so no `[host]:port` formatting is involved. |
| `modules/connection.py:506` | `open_ssh/_claim/_take_slot/get_persistent_connection/get_device_send_lock` | M | works | READ | sessions, budgets, locks and pools keyed by the ip string; Netmiko ConnectHandler(ip=2001:db8::1) is resolved by paramiko via getaddrinfo, no AF_INET assumption. |
| `modules/host_keys.py:336` | `check/policy/read` | M | works | READ | the store is JSON keyed by the exact address string (not known_hosts `[host]:port` text); an IPv6 literal is a key like any other, comparison is by key fingerprint. |
| `modules/job_health.py:1341` | `ssh_session_rows` | M | works | READ | opaque carrier: unit f"ssh:{ip}" and address shown; nothing splits the unit on ":". |
| `modules/nsot/rekey_op.py:115` | `plan` | M | works | READ | Opaque carrier to host_keys.held and connection.read_host_key (another group's sites). |
| `modules/nsot/rekey_op.py:175` | `apply` | M | works | READ | Opaque carrier to host_keys.replace; verify likewise. |
| `modules/nsot/retire.py:318` | `_host_key_facts` | M | works | READ | Opaque carrier to host_keys.forget_plan. |

#### deploy-verify-rollback (36 sites: 12 break, 0 unknown, 24 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/nsot/blast_radius.py:127` | `host_networks` | M | BREAKS | READ | `a.family != socket.AF_INET or not a.netmask` skips every IPv6 address; on an IPv6-only host Mercury has no networks and every reload's blast radius reads "unknown". |
| `modules/nsot/blast_radius.py:42` | `_attachments` | M | BREAKS | READ | Reads only interface `ipv4` ("A M"); IPv6-only intent yields no attachments, so no device is on any of Mercury's networks. |
| `modules/nsot/blast_radius.py:60` | `_addresses` | M | BREAKS | READ | Reads only `ipv4`; no caller (dead code), so no current effect. |
| `modules/nsot/deploy.py:1050` | `rollback_commands` | D | BREAKS | CHECKED | Undoing a pushed `ipv6 address 2001:DB8::2/64` emits ` ipv6 address 2001:DB8::1/64` (the existing line, via _previous) instead of `no ipv6 address 2001:DB8::2/64`; the added address survives rollback. |
| `modules/nsot/deploy.py:212` | `classify_diff` | D | BREAKS | CHECKED | Target 2001:DB8::2/64 vs running ::1/64 is classified "replace" (old→new); IOS keeps both, so the old address becomes unreported residue and the preview misstates the result. |
| `modules/nsot/deploy.py:781` | `_command_keys` | D | BREAKS | CHECKED | Precise key drops the last token, so every `ipv6 address X/len` on an interface shares key `ipv6 address`; IOS addresses are additive, but the tool treats a new one as replacing the old (see classify_diff, rollback). |
| `modules/nsot/expected_effects.py:120` | `_interface_networks` | D | BREAKS | READ | Parses only interface `ipv4` "A M"; an IPv6 BGP peer on a shut interface's IPv6 subnet is not predicted as a drop, so verify meets an unexpected BGP drop. |
| `modules/nsot/removal.py:217` | `_in_context` | D | BREAKS | READ | Already registered C554: named-acl.entry's header allows `ipv6 access-list` but the context requires `ip access-list `, so every IPv6 ACL entry is refused as unmeasured (safe direction). |
| `modules/nsot/removal.py:386` | `_management_interfaces` | M | BREAKS | READ | Only `ip address <mgmt_ip>`/`ip address dhcp` mark the management interface; one carrying `ipv6 address 2001:DB8::5/64` (or dhcp/autoconfig) is not protected, so Mode B may remove lines on the management path. |
| `modules/nsot/verify_scope.py:108` | `read_back` | D | BREAKS | CHECKED | Exact-text compare against running config: IOS prints IPv6 upper-case compressed, so a sent `ipv6 address 2001:db8::1/64` or `ipv6 route ::/0 2001:db8:0::ffff` reads "did not land" and verify fails (rollback). |
| `modules/pipeline.py:2514` | `_capture_operational_snapshot/_read_route_total/_await_route_retention/_parse_route_total` | D | BREAKS | READ | route retention reads only `show ip route summary`; IPv6 routes are never counted, so a deploy that loses IPv6 routes verifies as retained (an IPv6-only device compares 0 against 0). |
| `modules/pipeline.py:2694` | `_read_routing_protocols` | D | BREAKS | READ | EIGRP is read only by `show ip eigrp neighbors` with row regex `\s*\d+\s+\d+\.\d+\.\d+\.\d+`; EIGRP for IPv6 (`show ipv6 eigrp neighbors`, link-local rows) is never read or verified. |
| `modules/bgp_summary.py:45` | `parse_bgp_summary` | D | works | CHECKED | (MISSED BY SCAN) is_address accepts ":" and a wrapped IPv6 neighbour row is joined; an IPv6 Unicast peer parsed as established (neighbour kept in the device's upper-case spelling). |
| `modules/drift_check.py:497` | `_check_one` | M | works | READ | opaque carrier: dev["ip"] passed to the connection layer. |
| `modules/goldens.py:170` | `_identity_for_ip` | M | works | READ | opaque carrier: exact ip string compare against the inventory. |
| `modules/host_keys.py:446` | `netconf_args/netconf_refusal` | M | works | READ | ncclient compares the pinned key blob directly (hostkey_b64) and connects with getaddrinfo(AF_UNSPEC), so an IPv6 host needs no bracketed known_hosts entry. |
| `modules/nsot/blast_radius.py:103` | `radius` | M | works | READ | ipaddress.ip_network of either family; would work if fed IPv6 attachments and networks. |
| `modules/nsot/expected_effects.py:107` | `_ospf_on` | D | works | READ | Matches `ipv6 ospf N area` and `ospfv3 N ipv6 area` as well as `ip ospf N area`. |
| `modules/nsot/expected_effects.py:179` | `for_device` | D | works | READ | ip_address of either family with a version check before subnet membership; IPv6 BGP peers handled once _interface_networks supplies IPv6 subnets. |
| `modules/nsot/expected_effects.py:201` | `_addr` | D | works | CHECKED | Canonicalises via ipaddress (2001:DB8::0001 → 2001:db8::1), so BGP drop keys compare by value. |
| `modules/nsot/expected_effects.py:266` | `offers` | D | works | READ | BGP identities keyed through _addr, family-neutral; raw_of, verify_checks and declared_from carry the address opaquely. |
| `modules/nsot/reload_op.py:290` | `_wait_for_ssh` | M | works | READ | socket.create_connection((ip, 22)) resolves an IPv6 literal through getaddrinfo and opens AF_INET6. |
| `modules/nsot/reload_op.py:432` | `run` | M | works | READ | Opaque carrier of the device ip to _wait_for_ssh and the session. |
| `modules/nsot/removal.py:265` | `<file>` | M | works | READ | MANAGEMENT_GLOBAL refuses `^ip(v6)? route` and SHAPES carry global.ipv6-route, ipv6 ospf cost and ipv6 rip shapes: IPv6 parity for routes. |
| `modules/nsot/removal.py:504` | `removal_program` | M | works | READ | Opaque carrier of mgmt_ip to _management_interfaces (breaks there); with_removals, removable and candidates likewise. |
| `modules/nsot/restore.py:132` | `build_targets` | M | works | READ | Opaque carrier of the inventory ip (inventory.is_stale is another group's site). |
| `modules/nsot/verify_scope.py:41` | `classify` | D | works | CHECKED | Families keyed on command words (logging, ntp, snmp-server, line vty, ip tftp/ssh source-interface): `logging host ipv6 …`/`ntp server 2001:…` are QUICK; `ipv6 address` on an interface is FULL exactly as `ip address` is. |
| `modules/pipeline.py:1020` | `_canary_sanity_check` | D | works | READ | (MISSED BY SCAN) `show ip interface brief` lists every interface (an IPv6-only one shows unassigned) and only the up/up columns are read, so it is address-family neutral. |
| `modules/pipeline.py:2611` | `_parse_ospf_neighbor_rows` | D | works | READ | the dotted-quad match is on the Neighbor ID column, a 32-bit router id in both `show ip ospf neighbor` and `show ospfv3 neighbor`: correct for IPv6. |
| `modules/pipeline.py:2626` | `_parse_ripng_next_hops` | D | works | READ | regex `([0-9A-Fa-f:.]+)/(\S+)` reads RIPng's link-local next hops from `show ipv6 rip next-hops`. |
| `modules/pipeline.py:846` | `_stage_deploy/_stage_verify/_stage_rollback/_await_neighbour_convergence/_await_move/_await_interfaces/_watch_bgp_hold/_push_config/_stage_save_startup/_stage_save_golden/_stage_ci_gate/_stage_config_diff/_stage_pre_snapshot/_stage_post_snapshot/_capture_failure_state/_note_rolled_back_intent/_stage_audit_log/_record_pre_change/_stage_netbox_query/_canary_sanity_check` | M | works | READ | opaque carrier: devices are found by `d["ip"] == ip` string equality and the ip is passed to connection/host_keys; no parsing or formatting. |
| `modules/pipeline.py:949` | `_push_via_netconf` | M | works | READ | nc_mgr.connect(host=dev["ip"], port=830): ncclient's ssh transport resolves with socket.getaddrinfo(host, port, AF_UNSPEC), so an IPv6 literal works. |
| `routes/deploy.py:1219` | `_deploy_one` | M | works | READ | The pipeline context is keyed by device.get("ip") (eleven dicts): opaque keys, consistent within one run because every key is the same inventory string. Correct only while one spelling is used; see the canonical-form note. |
| `routes/deploy.py:553` | `plan_devices` | M | works | READ | Opaque carrier of the inventory ip as mgmt_ip into the program builder (judged in its `modules/nsot/` row). |
| `routes/golden.py:229` | `_capture_entry` | M | works | READ | Opaque carrier of the inventory ip. |
| `scripts/nmas-removal-probe:230` | `<file>` | D | works | READ | The probe already carries an `ipv6 route 2001:DB8:FFFF::/48 Null0` shape and IPv6 OSPF/RIP shapes; the gap is C554 (ipv6 access-list), registered. |

#### adopt (12 sites: 2 break, 0 unknown, 10 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/nsot/adopt.py:843` | `_plan` | M | BREAKS | READ | (spelling) `(r.get("ip") or "") == mgmt_ip`, `entry.get("mgmt_ip") == mgmt_ip` and find_by_ip: an IPv6 address typed in another spelling than the inventory holds passes not_managed/name_free, so a device can be adopted twice. |
| `modules/nsot/manifest.py:360` | `find_by_ip` | M | BREAKS | READ | (spelling) `entry.get("mgmt_ip") == mgmt_ip`, exact text; used by adopt and resolve_identity, so the same IPv6 address in another case/compression resolves to no device. |
| `modules/nsot/adopt.py:1166` | `apply` | M | works | READ | Opaque carrier (device_ops.hold ip=, _apply). |
| `modules/nsot/adopt.py:1251` | `_tool` | M | works | READ | Opaque key to credentials.resolve. |
| `modules/nsot/adopt.py:1322` | `_apply` | M | works | READ | Opaque carrier of mgmt_ip to the session, capture, persist, upsert_device and save_golden; no parsing. |
| `modules/nsot/adopt.py:1480` | `recover_tool_account` | M | works | READ | Opaque carrier of the sidecar's ip. |
| `modules/nsot/adopt.py:198` | `add_tool_account` | M | works | READ | Opaque carrier into the device dict. |
| `modules/nsot/adopt.py:315` | `_add_tool_account` | M | works | READ | Opaque carrier into write_sidecar and the credential record. |
| `modules/nsot/adopt.py:552` | `write_sidecar` | M | works | READ | Stores the address as an opaque JSON string. |
| `modules/nsot/adopt.py:748` | `plan` | M | works | READ | Opaque carrier to _plan. |
| `routes/adopt_v2.py:67` | `preview` | M | works | READ | Opaque carrier of mgmt_ip to adopt.plan (judged in its `modules/nsot/` row). |
| `templates/v2/_adopt.html:79` | `<template>` | M | works | READ | Free text, no pattern attribute; acceptance decided server-side in adopt.plan (judged in its `modules/nsot/` row). |

#### monitoring (32 sites: 11 break, 2 unknown, 19 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/drained.py:136` | `judge` | M | BREAKS | READ | `mgmt_ip in i["address"]` exact match against the IPv4-only list: a device managed over IPv6 is always "not judged" (its management path is never known). |
| `modules/drained.py:75` | `interfaces_from_goldens` | M | BREAKS | READ | git grep collects only `^ ip address ` lines, never `ipv6 address`, so an IPv6 management address is never found in the golden (and parts[2] would carry /len); module is off today (ENABLED False). |
| `modules/integrations/monitoring_profile.py:38` | `sntp_answers` | H | BREAKS | READ | socket.socket(AF_INET, SOCK_DGRAM) then sendto((host,123)); an IPv6 NTP server can never answer, reported "no answer". |
| `modules/integrations/monitoring_profile.py:57` | `tcp_accepts` | H | BREAKS | CHECKED | addr.rpartition(":") leaves the brackets: "[2001:db8::1]:57000" connects to ("[2001:db8::1]", 57000), which cannot resolve, so the Telegraf listener check always fails. |
| `modules/nsot/ip_sla_policy.py:147` | `gateway` | D | BREAKS | READ | Only `family == "ipv4"` and spec `0.0.0.0 0.0.0.0 <hop>`; an `ipv6 route ::/0 <hop>` default is never a gateway target. |
| `modules/nsot/ip_sla_policy.py:162` | `static_hop` | D | BREAKS | READ | Skips every route whose family is not ipv4, so an IPv6-only device has no static hop. |
| `modules/nsot/ip_sla_policy.py:185` | `rip_peers` | D | BREAKS | READ | nets() reads only interface `ipv4`; RIPng peers are never implied. |
| `modules/nsot/ip_sla_policy.py:246` | `targets` | D | BREAKS | READ | `if e.get("proto") == "ospfv3": continue` ("the same peers as OSPF"); on an IPv6-only network OSPFv3 peers are the only peers, so `peers`/`upstream` name nothing. |
| `modules/nsot/ip_sla_policy.py:74` | `router_address` | D | BREAKS | READ | Uses Loopback0's `ipv4` only, else falls back to the OSPF router-id: on IPv6-only a 32-bit router id (not an address) becomes the icmp-echo target. |
| `modules/nsot/profile_propose.py:239` | `connector_value` | H | BREAKS | READ | `recv.rsplit(":", 1)` on telemetry_receiver: "[2001:db8::9]:57000" keeps the brackets, rendering `receiver ip address [2001:db8::9] 57000` (invalid); an unbracketed IPv6 receiver is ambiguous. |
| `modules/readers/reachability.py:78` | `probe` | M | BREAKS | READ | ping3 is AF_INET only (gethostbyname -> HostUnknown -> False), so an IPv6 device is never ICMP-reachable; TCP:22 via create_connection answers, so a device with SSH closed reads unreachable on IPv6 only. |
| `deploy/snmp_exporter/routing-modules.yml:10` | `cisco_bgp_peer2` | D | unknown | READ | cbgpPeer2RemoteAddr index type InetAddress (generator v0.29.0); its label text for a 16-octet address decides neighbours.reported; same measurement: one IPv6 peer's label value in Prometheus. |
| `modules/prometheus_targets.py:142` | `generate` | M | unknown | READ | file_sd target written bare (`"targets": ["2001:db8::1"]`, no brackets); settle by one scrape of the installed snmp_exporter with target=2001:db8::1 through the host's relabel config. |
| `deploy/grafana/build_nmas_device.py:38` | `<file>/build` | M | works | READ | every panel selects `device="$device"` (hostname) and the syslog panel matches `\d+: $device: `; no `instance` matcher, so the address family does not matter (nmas-device.json is its output). |
| `deploy/snmp_exporter/routing-modules.yml:68` | `ospf/ospfv3` | D | works | READ | ospfNbrIpAddr/ospfNbrRtrId InetAddressIPv4 are OSPFv2 (IPv4 by definition); ospfv3NbrRtrId is a 32-bit gauge; no IP-MIB/IPV6-MIB address table is walked at all. |
| `modules/attention.py:1471` | `_member/_inventory/reachability_source/adjacency_source/job_health_source` | M | works | READ | alert's polled `instance` looked up by exact string in {inventory ip: hostnames}; a bare IPv6 instance equal to the inventory spelling matches. |
| `modules/device_page.py:473` | `alerts_check/answering/checks` | M | works | READ | exact `i.get("address") == ip` and reachability lookup by ip string; works when the instance equals the inventory spelling. |
| `modules/device_page.py:613` | `variable_value` | M | works | READ | address placed raw into the dashboard variable by panels.interpolate; colons are not regex-special in a `=~` matcher, and the default value_from is hostname. |
| `modules/drained.py:117` | `_covers` | D | works | READ | IPv4Address on OSPFv2 `network <net> <wildcard> area` statements, which are IPv4 by definition; OSPFv3 areas come from the interface's own `ipv6 ospf ... area`. |
| `modules/drained.py:188` | `queries/_alternatives/since_query/_by_interface/measure` | M | works | CHECKED | re.escape leaves ":" alone, so instance=~"2001:db8::1" and instance="2001:db8::1" are valid PromQL; series are mapped back by exact instance string. |
| `modules/integrations/prometheus.py:59` | `targets_for` | M | works | READ | host() strips [v6]:port brackets and keeps a bare v6 whole (count(":")==1 guard); match is exact text, so the device list and Prometheus must spell the address the same way. |
| `modules/monitoring_coverage.py:37` | `configured` | D | works | CHECKED | (MISSED BY SCAN) `^logging host \S+` matches `logging host ipv6 2001:db8::1`; `snmp-server community` carries no address. |
| `modules/neighbours.py:77` | `query/rows_of` | M | works | READ | adjacency series selected by the `device` label (hostname), not by address. |
| `modules/nsot/ip_sla_policy.py:209` | `_owner` | D | works | READ | ipaddress.ip_address of either family against neighbours.addresses. |
| `modules/nsot/parsers/base.py:500` | `_h_snmp` | D | works | CHECKED | (MISSED BY SCAN) `snmp-server host 2001:DB8::8 version 2c …` captured with address 2001:DB8::8. |
| `modules/nsot/profile_propose.py:254` | `connector_value` | H | works | READ | snmp_trap_host and ntp_servers are carried opaquely into `snmp-server host`/`ntp server`, both valid IOS for IPv6 literals. |
| `modules/nsot/retire.py:582` | `targets_after` | M | works | READ | Matches the `device` label first; the address membership in targets is only an exact-string fallback. |
| `modules/nsot/templates/_common.j2:210` | `<file>` | D | works | READ | `snmp-server host {{ h.address }}` is valid IOS for an IPv6 trap host. |
| `modules/prometheus_targets.py:309` | `compare/_differences` | M | works | READ | targets compared by the instance label against the inventory string; equal when the relabel copies the bare target into instance verbatim. |
| `modules/readers/grafana_alerts.py:151` | `_instance_device` | M | works | READ | opaque carrier: the `instance` label copied as the alert's address, no parsing. |
| `modules/readers/reachability.py:110` | `population` | M | works | READ | ipaddress.ip_address accepts both families; unspecified/multicast filtered for either. |
| `modules/readers/restarts.py:75` | `prometheus_series` | M | works | READ | sysUpTime read and grouped by the `device` label, never by address. |

#### silences (4 sites: 2 break, 0 unknown, 2 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/acknowledgements.py:106` | `devices_of` | M | BREAKS | CHECKED | `host_by_address.get(val.split(":")[0])` strips a port by first colon: an IPv6 instance becomes "2001", so an acknowledged alert row maps to no device (IPv4 maps correctly). |
| `modules/restarts.py:270` | `_matchers` | M | BREAKS | CHECKED | instance regex `(2001:db8::1)(:[0-9]+)?` matches a bare IPv6 instance but never the `[2001:db8::1]:port` form an exporter with a port writes, so such alerts are not silenced (IPv4 `a.b.c.d:port` is). |
| `modules/integrations/grafana.py:191` | `_put_silence` | M | works | READ | Matcher values opaque, isEqual exact; the instance value is composed in modules/restarts.py (other group). |
| `modules/restarts.py:257` | `_targets/_move_silences` | M | works | READ | opaque carrier: inventory ip strings into the matcher; _move_silences re-sends the stored matcher via partition("=~"), unaffected by colons. |

#### logs (10 sites: 3 break, 2 unknown, 5 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/nsot/parsers/base.py:544` | `_h_logging` | D | BREAKS | CHECKED | (MISSED BY SCAN) `host\s+(\S+(?:\s+vrf\s+\S+)?)$` fails on IOS's `logging host ipv6 2001:DB8::9`; it lands in logging.settings, the syslog block has no host, and syslog_block_problems refuses the intent as partial. |
| `modules/nsot/templates/_common.j2:201` | `<file>` | D | BREAKS | READ | (MISSED BY SCAN) `logging host {{ h }}` (also line 195) for syslog.hosts; an IPv6 syslog_host (onboard.syslog_baseline) renders `logging host 2001:db8::9`, but IOS's IPv6 form is `logging host ipv6 <addr>`. |
| `scripts/host-steps/c788-loki-writer-rotate.sh:127` | `<file>` | H | BREAKS | READ | keys.py prints and rewrites f"{u.hostname}:{u.port}"; urlsplit().hostname drops brackets, so a v6 MinIO endpoint becomes "2001:db8::5:9000" in Loki's config and in boto3's endpoint_url (c788-undo reads the same). |
| `scripts/host-steps/c722-device-label.sh:45` | `<file>` | M | unknown | READ | (MISSED BY SCAN) Trap `device` label is the first name-shaped token ([A-Za-z][A-Za-z0-9._-]* then " ["); an unresolved v6 source address cannot match; measure one trap from a v6-only device in snmptrapd's journal line. |
| `scripts/host-steps/ibn7-severity-trap-label.sh:88` | `<file>` | M | unknown | READ | (MISSED BY SCAN) Same trap device regex as c722 (rewrites that Alloy config); same measurement settles it. |
| `deploy/rsyslog/10-network-devices.conf:20` | `<file>` | H | works | READ | imudp with no address listens on both families by default; the dynafile /var/log/network/<FROMHOST-IP>.log takes colons; nothing downstream parses the file name (Alloy labels by the hostname in the line). One line from an IPv6 source confirms. |
| `modules/device_logs.py:191` | `selector/for_device/change_lines` | M | works | READ | a device's lines are selected by its hostname (origin-id pattern) or the `device` label, never by syslog source address, so IPv6 transport is irrelevant. |
| `modules/history_sources.py:720` | `_hosts_by_address` | M | works | READ | opaque carrier: {inventory ip: hostname} built for devices_of (which breaks on IPv6). |
| `modules/settings_schema.py:208` | `<file>` | M | works | READ | loki_selector_template `{host="{ip}"}` places the address inside a quoted label value, valid for an IPv6 literal. |
| `scripts/host-steps/c722-device-label.sh:60` | `<alloy config>` | H | works | READ | (MISSED BY SCAN as an address site; scanned only as a path) The device label comes from the hostname in the syslog line, never the source address, so an IPv6 sender is labelled the same way. |

#### path-trace (8 sites: 7 break, 0 unknown, 1 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/path_trace.py:144` | `owners` | D | BREAKS | CHECKED | `if ":" in str(addr): continue` drops every IPv6 intent address and IPv6 BGP peering, so an IPv6 next hop is never attributed to a device (owners() returns {} for an IPv6-only node). |
| `modules/path_trace.py:156` | `destinations` | D | BREAKS | READ | `":" in addr` skips IPv6 peerings and loopbacks, so the To list offers nothing on an IPv6-only network. |
| `modules/path_trace.py:32` | `<file>` | D | BREAKS | READ | (MISSED BY SCAN) COMMAND = "show ip cef {dest}" is the only command a trace sends; there is no `show ipv6 cef` path, so an IPv6 destination can never be read hop by hop. |
| `modules/path_trace.py:413` | `refusal` | D | BREAKS | CHECKED | `if addr.version != 4` refuses every IPv6 destination by name ("the trace reads IPv4 forwarding only"). |
| `modules/path_trace.py:422` | `start` | D | BREAKS | READ | `dest = str(ipaddress.IPv4Address(dest))` would raise on an IPv6 destination (unreachable today only because refusal() stops it first). |
| `modules/path_trace.py:54` | `parse_cef` | D | BREAKS | CHECKED | (MISSED BY SCAN) _VIA = `via\s+([0-9.]+),` accepts only dotted digits, so a `via 2001:db8::2, Gi2` next hop line never matches. |
| `modules/path_trace.py:56` | `parse_cef` | D | BREAKS | CHECKED | `_PREFIX` dotted-quad regex and `ipaddress.IPv4Address(hm.group(1))` on each next hop: an IPv6 cef answer (2001:DB8:2::/64, nexthop FE80::2) parses to state unknown, prefix "" and no hops. |
| `modules/path_trace.py:266` | `trace/answer_words` | D | works | READ | opaque carrier: next-hop addresses are looked up in owner_of by string and printed; no family assumption beyond what parse_cef/owners produce. |

#### rotation (12 sites: 1 break, 1 unknown, 10 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/nsot/credential_rotation.py:1264` | `_yang_push_consumer` | M | BREAKS | READ | HOST default found only by a dotted-quad regex; an IPv6 HOST is never matched and the report claims "its default target is another device" instead of unknown (consumer retired here, C31, path live when applicable). |
| `scripts/nmas-credential-overrides:91` | `claimed_keys` | M | unknown | READ | Claims keys by the raw ip/mgmt_ip string: case and compression differences between sources would be two claims. Maintenance script. |
| `modules/connection.py:568` | `read_host_key` | M | works | READ | socket.create_connection((ip, port)) uses getaddrinfo and opens AF_INET6 for an IPv6 literal; paramiko.Transport takes the socket. |
| `modules/host_keys.py:241` | `names_for/holders/forget_plan` | M | works | READ | exact `.strip() == ip` string compares against inventory and manifest; correct for IPv6 when every source spells the address the same (no canonicalisation: 2001:DB8::1 vs 2001:db8::1 would not match). |
| `modules/nsot/credential_rotation.py:1170` | `plan` | M | works | READ | Opaque carrier of mgmt_ip. |
| `modules/nsot/credential_rotation.py:1220` | `consumer_report` | M | works | READ | Opaque carrier of mgmt_ip to _yang_push_consumer. |
| `modules/nsot/credential_rotation.py:1469` | `_rotate` | M | works | READ | Opaque carrier of the device ip. |
| `modules/nsot/credential_rotation.py:1700` | `_commit` | M | works | READ | Opaque key to credentials.set_device_override and GoldenItem. |
| `modules/nsot/credential_rotation.py:1895` | `save_on_device` | M | works | READ | Opaque carrier to onboard.persist_on_device; _persist and persist likewise. |
| `modules/nsot/credential_rotation.py:2120` | `recover_staged` | M | works | READ | Opaque carrier to device_ops.hold. |
| `modules/nsot/credential_rotation.py:987` | `preflight` | M | works | READ | Opaque carrier of the inventory ip (inventory.is_stale is another group's site). |
| `modules/nsot/rotate_op.py:122` | `run` | M | works | READ | Opaque carrier of mgmt_ip to credential_rotation.persist. |

#### dhcp (43 sites: 7 break, 0 unknown, 36 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/dhcp_exclusions.py:101` | `span` | M | BREAKS | CHECKED | Accepts one address or a-b only; a pool Kea reports in prefix form (2001:db8:1::/112, the usual v6 pool) is refused, so _plan refuses and conflicts() silently skips that pool (family-neutral defect). |
| `modules/dhcp_reservations.py:487` | `_plan` | M | BREAKS | READ | (MISSED BY SCAN) Lease-holder and duplicate checks are text equality (`l.get("ip-address") == address`, `address in r["addresses"]`, also 427/471) against Kea's canonical text; a non-canonical v6 spelling (2001:db8:0::10) passes "leased to no one". |
| `modules/nsot/bootstrap_config.py:279` | `manager_interface_lines` | M | BREAKS | READ | The DHCP/ZTP sentinel renders only ` ip address dhcp`; there is no `ipv6 address dhcp`/`ipv6 address autoconfig`, so a DHCP-sourced device on an IPv6-only segment gets no management address. |
| `modules/nsot/onboard.py:2584` | `discover_dhcp_address` | M | BREAKS | READ | (spelling) `lease["address"] != reserved`: for a ZTP device `reserved` is the typed address and the lease is Kea's canonical text, so a non-canonical IPv6 spelling refuses as a disagreement. |
| `scripts/nmas-kea-lifetimes:109` | `main` | H | BREAKS | READ | Requires kea_config for both families and Disc.segment(configs["IPv4"]) before planning; with no dhcp4 or no IPv4 ZTP subnet it exits before the IPv6 lifetimes. |
| `scripts/nmas-kea-reservation-files:48` | `main` | H | BREAKS | READ | (MISSED BY SCAN) Loops IPv4 first and returns 2 when dhcp4's config-get fails, so on a dhcp6-only Kea the IPv6 reservation files are never planned. |
| `scripts/nmas-kea-subnet-files:50` | `snapshot` | H | BREAKS | READ | (MISSED BY SCAN) Loops both families and D.kea_config raises when a family cannot be asked, so a Kea serving dhcp6 alone makes the host step stop (exit 2) before the IPv6 move. |
| `modules/dhcp_exclusions.py:279` | `_plan` | M | works | READ | Range and lease checks with ip_address/ip_network of either family; holder by hw-address or duid; kea-dhcp6 -t for IPv6. |
| `modules/dhcp_exclusions.py:363` | `conflicts` | M | works | READ | Intent addresses canonicalised with ip_address, v6 prefix keys lowercased; only its pool spans go through span (see :101). |
| `modules/dhcp_lifetimes.py:48` | `<file>` | M | works | READ | Class files, subnet keys and wanted globals per family; IPv6 gets preferred lifetimes. |
| `modules/dhcp_page.py:141` | `pool_size` | M | works | CHECKED | Range or prefix of either family counted by int(); 2001:db8::/120 plus a 16-address range gives 272. |
| `modules/dhcp_page.py:239` | `view` | M | works | READ | Reservation/lease joins compare Kea's own canonical text on both sides, per service; split(":") is on the family:id key. |
| `modules/dhcp_page.py:350` | `gateway` | M | works | READ | IPv6 subnets shown with the routers' RA M/O flags from intent rather than a gateway option. |
| `modules/dhcp_page.py:385` | `duid_words` | M | works | CHECKED | Decodes DUID-LL and DUID-LLT to the MAC. |
| `modules/dhcp_page.py:419` | `_addr_key` | M | works | READ | Sort key (version, int) of either family. |
| `modules/dhcp_page.py:469` | `_reservation_now` | M | works | READ | Lease and reservation addresses both from Kea config-get/lease-get (canonical), per svc. |
| `modules/dhcp_reservations.py:193` | `every_reservation` | M | works | READ | Walks the family's subnet key and shared networks; ip-address and ip-addresses both read. |
| `modules/dhcp_reservations.py:219` | `_in` | M | works | READ | ip_address in ip_network, either family (also used by stranded). |
| `modules/dhcp_reservations.py:241` | `_pool_holds` | M | works | READ | Pool as range or prefix, ip_address comparisons of either family. |
| `modules/dhcp_reservations.py:281` | `ask` | M | works | CHECKED | `where` split(":",1) is the family:id selector; a v6 address is lowercased (not canonicalised: see _plan:487). |
| `modules/dhcp_reservations.py:294` | `_entry` | M | works | READ | IPv6 reservation written as ip-addresses: [address], IPv4 as ip-address. |
| `modules/dhcp_reservations.py:42` | `<file>` | M | works | READ | FAMILY covers dhcp4/subnet4/lease4 and dhcp6/subnet6/lease6; OFFERED lets IPv6 reserve by duid or hw-address. |
| `modules/dhcp_subnets.py:28` | `<file>` | M | works | READ | FILES maps IPv4→subnet4 and IPv6→subnet6; every planner keys on the family. |
| `modules/dhcp_subnets.py:309` | `_pool` | M | works | READ | ip_address on both ends, refused unless the same version as the prefix and inside it. |
| `modules/dhcp_subnets.py:329` | `pool_span` | M | works | CHECKED | Accepts a-b or a prefix pool of either family (2001:db8:1::/112 gives first/last). |
| `modules/dhcp_subnets.py:348` | `_set_option` | M | works | READ | Option space dhcp4 or dhcp6 by family. |
| `modules/dhcp_subnets.py:442` | `_settings` | M | works | READ | Gateway and DNS validated with ip_address/ip_network of either family; IPv6 gets preferred-lifetime. |
| `modules/dhcp_subnets.py:491` | `_plan_add` | M | works | READ | ip_network(strict) with a version check against the family; overlap per family's subnet key; v6 intent keyed lowercase. |
| `modules/dhcp_subnets.py:581` | `_plan_remove` | M | works | READ | Lease holders named by hostname, hw-address or duid. |
| `modules/dhcp_subnets.py:639` | `_plan_edit` | M | works | READ | Lease addresses compared as ip_address objects. |
| `modules/integrations/kea.py:57` | `command` | H | works | READ | Service list from the caller or the kea_services setting (default ["dhcp4"]); callers that omit it (reservation_for's config-get) ask dhcp4 only. |
| `modules/nsot/ztp.py:482` | `_run_kea_test` | H | works | READ | Takes `program`, so kea-dhcp6 is testable (DHCP's IPv6 reservations, C529); only the ZTP writer's call keeps the kea-dhcp4 default (counted at _config_test). |
| `modules/readers/dhcp.py:233` | `facts_from` | D | works | READ | IPv4 "A M" via ip_interface; each IPv6 address via ip_interface, fe80 skipped, prefix key lowercased. |
| `modules/readers/dhcp.py:263` | `leases` | M | works | READ | Identity per family, prefix-len and iaid kept for DHCPv6. |
| `modules/readers/dhcp.py:31` | `<file>` | M | works | READ | FAMILIES reads dhcp4 and dhcp6 each on its own, lease4/lease6, identities per family (DUID first for IPv6). |
| `modules/readers/dhcp.py:89` | `reservations` | M | works | READ | ip-address, ip-addresses and prefixes all carried. |
| `modules/settings_schema.py:227` | `<file>` | H | works | READ | kea_services defaults to ["dhcp4"] but the schema enum allows "dhcp6"; kea_dhcp6_config is declared; whether DHCPv6 paths work belongs to the DHCP group. |
| `scripts/host-steps/c529-step2-reservation-files.sh:59` | `<file>` | H | works | READ | Copies, tests and installs both kea-dhcp4 and kea-dhcp6 files (its tool needs both families answering: see nmas-kea-reservation-files). |
| `scripts/host-steps/c529-step5-subnet-files.sh:70` | `<file>` | H | works | READ | Both families' files handled (its tool needs both answering: see nmas-kea-subnet-files). |
| `scripts/host-steps/e19-dhcp-lifetimes.sh:61` | `<file>` | H | works | READ | Both families' files handled (its tool refuses without an IPv4 ZTP subnet: see nmas-kea-lifetimes). |
| `templates/v2/_dhcp_reserve.html:45` | `<template>` | M | works | READ | The reservation form offers hw-address, duid and client-id as the identity key: DUID reservations are already drawable. |
| `templates/v2/_dhcp_subnet.html:63` | `<template>` | M | works | READ | The subnet card already explains DHCPv6 has no gateway option and the route comes from RAs: the page is family-aware. |
| `templates/v2/_dhcp_view.html:107` | `<template>` | M | works | READ | Leases draw a DUID and IAID for IPv6 leases (C681): family-aware. |

#### netbox (30 sites: 7 break, 0 unknown, 23 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/device_netbox.py:109` | `for_device` | M | BREAKS | READ | The record carries primary_ip4 only and templates/v2/_netbox.html draws "Primary IPv4", so a v6-only device's NetBox tab shows "—" though primary_ip6 is set. |
| `modules/inventory/netbox_source.py:130` | `adapt_devices` | M | BREAKS | CHECKED | mgmt_ip = primary_ip4 only; a device with only primary_ip6 is skipped "no primary IPv4 address set in NetBox" (_address_only's split("/") itself handles v6). |
| `modules/netbox_client.py:2433` | `_upsert_device` | M | BREAKS | READ | (MISSED BY SCAN) The exact-match tier `intf["cidr"].split("/")[0] == ip` runs only for the IPv4 cidr; the IPv6 loop never compares to ip, so a v6 management address is never chosen by match. |
| `modules/netbox_client.py:2656` | `_upsert_device` | M | BREAKS | READ | Fallbacks set only primary_ip4: tier 1 finds the v6 object by address=ip and PATCHes it as primary_ip4 (NetBox refuses the family); tier 3 builds f"{ip}/32" for a v6 address (wrong length) and also targets primary_ip4. |
| `modules/netbox_client.py:2694` | `_upsert_device` | M | BREAKS | READ | primary_ip6 = loopback_ipv6_id or first_ipv6_id, never the management (SSH) address; the comment states "this app doesn't manage over IPv6". |
| `modules/netbox_client.py:2935` | `_parse_static_routes_from_config` | D | BREAKS | CHECKED | Regex is `^ip route` with dotted network and mask and IPv4Network; `ipv6 route` lines are never read, so IPv6 static routes never reach NetBox IPAM. |
| `templates/v2/_netbox.html:28` | `<template>` | M | BREAKS | READ | The device's NetBox tab draws "Primary IPv4" from r.primary_ip4 only: an IPv6-only device shows a dash, so the tab says it has no primary address. |
| `modules/netbox_client.py:1172` | `_ensure_prefix` | D | works | READ | Prefix string passed opaque to NetBox ipam/prefixes, which stores either family. |
| `modules/netbox_client.py:1323` | `_ensure_ip_address` | D | works | READ | Lookup scoped to the interface and matched by _same_address (ip_interface, either family); payload address is the opaque CIDR. |
| `modules/netbox_client.py:1378` | `_same_address` | D | works | CHECKED | ip_interface comparison; 2001:DB8::1/64 equals 2001:db8::1/64. |
| `modules/netbox_client.py:1930` | `_build_config_context` | D | works | READ | Opaque carrier: mgmt_ip stored as a string in local_context_data. |
| `modules/netbox_client.py:2457` | `_upsert_device` | D | works | READ | Each parsed `ipv6 address` gets its prefix (ip_interface().network) and an IP object on its interface, same VRF. |
| `modules/netbox_client.py:2761` | `_parse_all_interfaces_from_config` | D | works | CHECKED | `ipv6 address X/len` lines parsed via ip_interface beside `ip address A M` and secondaries; caveat: `X/len eui-64` is recorded as X/len itself (the subnet-router anycast), link-local/dhcp/autoconfig skipped. |
| `modules/netbox_client.py:3139` | `_scan_device_from_golden` | M | works | READ | Opaque carrier of dev["ip"] and prefix_len (prefix_len comes from Kea lease_for, which is IPv4-only: see kea.py:258). |
| `modules/netbox_client.py:3289` | `_sync_list_to_netbox_impl` | M | works | READ | Opaque carrier: results keyed by the ip string. |
| `modules/netbox_client.py:4071` | `_compact_device` | M | works | READ | Returns both primary_ip4 and primary_ip6 addresses. |
| `modules/netbox_client.py:4142` | `_resolve_device` | M | works | READ | NetBox `address=` filter takes either family; split("/")[0] only strips a length. |
| `modules/netbox_client.py:4198` | `netbox_get_interfaces` | D | works | READ | Opaque carrier of NetBox address strings per interface. |
| `modules/netbox_client.py:4259` | `netbox_get_vpn_tunnels` | D | works | READ | Opaque carrier of the tunnel outside_ip address string. |
| `modules/netbox_client.py:722` | `_infer_prefix_role_name` | D | works | CHECKED | ipaddress.ip_network of either family; a v6 /127 is Point-to-Point (a /126 or /64 link gets no role, cosmetic). |
| `modules/nsot/adopt.py:680` | `_netbox_existing` | M | works | READ | Lists ipam/ip-addresses by device_id, family-neutral. |
| `modules/nsot/adopt.py:696` | `_netbox_dry_run` | M | works | READ | Opaque carrier to netbox_client.sync_list_to_netbox (another group's site). |
| `modules/nsot/context.py:68` | `_fetch_interfaces` | M | works | READ | Carries NetBox ip-address `address` and `family` of either family into the render context, unparsed. |
| `modules/nsot/onboard.py:1511` | `create_netbox_record` | M | works | READ | Carries ip and mgmt_prefix_len unparsed to netbox_client.sync_list_to_netbox (another group's site). |
| `scripts/nmas-netbox-census:203` | `_baseline_ids` | D | works | READ | Label "id:address" split(":",1)[0] takes the id before any v6 colon. |
| `scripts/nmas-netbox-ip-provenance:97` | `device_state` | M | works | READ | Reports both primary_ip4 and primary_ip6; audit() carries addresses opaque. |
| `scripts/nmas-netbox-repair-addresses:201` | `plan` | D | works | READ | Wanted set includes ipv6_addresses; compared with _same_address. |
| `scripts/nmas-netbox-repair-addresses:233` | `_holder_of` | D | works | READ | NetBox address= filter, either family. |
| `scripts/nmas-netbox-repair-addresses:292` | `excluded_residue` | M | works | READ | Protects both primary_ip4 and primary_ip6. |
| `scripts/nmas-netbox-repair-addresses:412` | `main` | D | works | READ | Opaque carrier to _ensure_ip_address. |

#### topology (16 sites: 2 break, 1 unknown, 13 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `modules/netbox_client.py:1582` | `_parse_cdp_neighbors` | D | BREAKS | CHECKED | _RE_CDP_IP is dotted-quad only, so a neighbour advertising only "IPv6 address:" yields remote_ip ""; no consumer reads remote_ip today (cables keyed on hostname), so no visible effect yet. |
| `modules/netbox_client.py:1593` | `_parse_lldp_neighbors` | D | BREAKS | READ | _RE_LLDP_IP "^\s*IP:\s*dotted" only; an LLDP "IPv6:" management address is ignored, remote_ip "" (unconsumed today, as for CDP). |
| `modules/neighbours.py:329` | `reported` | D | unknown | CHECKED | handles a colon-form cbgpPeer2RemoteAddr (2001:0DB8:...:0001 -> 2001:DB8::1, matched by _same) but not a hex or dotted-octet rendering; settle by reading one IPv6 BGP peer's cbgpPeer2RemoteAddr label in Prometheus. |
| `modules/neighbours.py:158` | `_v4/_covered/ospf_links` | D | works | READ | IPv4-only by design for OSPFv2 (`ip address A M` and `network <net> <wild> area` are IPv4 constructs); IPv6 interfaces are handled by ospfv3_links. |
| `modules/neighbours.py:217` | `ospfv3_links/addresses/bgp_peers/_peer_address/rip_protocols` | D | works | READ | ipaddress.ip_interface/ip_address of either family; link-local excluded from subnet matching; owners keyed by ip_address objects. |
| `modules/neighbours.py:305` | `_rid_from_int` | D | works | READ | IPv4Address(int) renders the OSPFv3 32-bit router id, which is dotted-quad in IPv6 networks too. |
| `modules/neighbours.py:352` | `_same/compare` | D | works | CHECKED | ipaddress.ip_address equality, so case and zero-compression differences compare equal (2001:0DB8:...:0001 == 2001:db8::1). |
| `modules/netbox_client.py:1787` | `_fetch_neighbors_live` | M | works | READ | Opaque carrier: dev["ip"] only in a log line; the session is opened by connection.get_persistent_connection (other group). |
| `modules/readers/adjacencies.py:89` | `_key/read` | D | works | READ | key joined with "\|" so a colon address cannot split it; address carried opaque. |
| `modules/readers/rip.py:54` | `_classful` | D | works | CHECKED | (MISSED BY SCAN) `int(str(address).split(".")[0])` is RIPv2's classful rule (IPv4 by definition); an IPv6 value raises ValueError, which rip_interfaces catches and skips. |
| `modules/readers/rip.py:72` | `rip_interfaces/read_device` | D | works | READ | RIP network statements and `ip address A M` are IPv4 by definition; RIPng is read separately with `show ipv6 rip next-hops`; ip passed opaque to open_ssh. |
| `modules/readers/topology_graph.py:201` | `_iface_networks/_iface_holding/routing_links/_peer_by_lldp/_area/_local_port/network_graph` | D | works | READ | ipaddress of both families with version checks; the BGP network key says ipv6 for a colon address; OSPFv2 area from network statements is IPv4 by definition. |
| `modules/readers/topology_graph.py:380` | `rip_links/subnets` | D | works | READ | RIP gateways are IPv4 (RIPv2); RIPng next hops are placed through IPv6 global subnets with link-local excluded. |
| `modules/readers/topology_graph.py:451` | `here` | H | works | READ | IPv4 by SIOCGIFADDR ioctl on an AF_INET socket plus IPv6 from /proc/net/if_inet6 (prefix length from the hex field), so an IPv6-only host is seen. |
| `modules/readers/topology_graph.py:553` | `manager_links` | H | works | READ | ip_interface of either family and `m.version == d.version and m.ip in d.network`: the host attaches by IPv6 subnet too. |
| `modules/topology_page.py:267` | `_neighbour_words` | D | works | READ | display carrier: " at {address}". |

#### other (69 sites: 11 break, 2 unknown, 56 work)

| Site | Function | Plane | Verdict | How | Why |
|---|---|---|---|---|---|
| `app.py:616` | `<file>` | H | BREAKS | READ | The printed URL is f"http://{FLASK_HOST}:{FLASK_PORT}" with only 0.0.0.0 special-cased: a bind of "::" prints http://:::5000 and the auto-opened browser URL is invalid. Cosmetic; the headless host only prints it. |
| `modules/identity.py:287` | `identify/trusted_peers` | H | BREAKS | READ | `peer in allowed` is exact string equality between REMOTE_ADDR and the typed list: an IPv6 peer matches only in the server's compressed lowercase text; another spelling, a zone id or a v4-mapped `::ffff:` peer is refused. |
| `modules/netbox_client.py:1394` | `_parse_ip_interfaces` | D | BREAKS | READ | _RE_INET_CIDR matches only dotted "Internet address is A/len", so an IPv6-only interface is dropped; DEAD CODE, no caller (the SSH scanner was removed in Stage 3.3). |
| `modules/netbox_client.py:1810` | `_parse_interfaces_from_running_config` | D | BREAKS | READ | _RE_RC_IP_ADDR + IPv4Network(A/M): only "ip address A M" lines, no "ipv6 address"; DEAD CODE, no caller (the live path is _parse_all_interfaces_from_config). |
| `modules/nsot/privileged.py:142` | `interfaces` | M | BREAKS | READ | Management interface found only by `^\s+ip address (\S+) \S+` equal to the inventory ip; with an IPv6 management address none is found, so a Tier 2 interface command is not refused on the management interface. |
| `modules/nsot/reads.py:537` | `<file>` | D | BREAKS | READ | COMMON offers only IPv4 reads (`show ip interface brief`, `show ip route`, `show ip ospf neighbor`, `show ip bgp summary`); no IPv6 counterpart (show ipv6 interface brief/route, ospfv3 neighbor, bgp ipv6 unicast summary). |
| `modules/nsot/tftp_once.py:63` | `serve_once` | M | BREAKS | READ | (spelling) `host not in clients` compares Python's canonical peer (with %zone for link-local) against --client text as typed; an upper-case or uncompressed IPv6 client is refused as "not the device". |
| `modules/settings_schema.py:98` | `<file>` | H | BREAKS | READ | flask_host default "0.0.0.0" (config.FLASK_HOST) binds IPv4 only, so on an IPv6-only network the web server is unreachable until set to "::" (accepted by the host field). |
| `scripts/host-steps/minio-root-rotate.sh:220` | `<file>` | H | BREAKS | READ | ENDPOINT.rpartition(":") keeps "[2001:db8::5]" while urlsplit().hostname has no brackets, so an mc alias holding the old root user on a v6 endpoint is never matched or removed. |
| `scripts/nmas-oxidized-cred:85` | `<file>` | M | BREAKS | READ | IPV4 regex and line.split(":") on router.db rows: an IPv6 row is refused. Oxidized was removed in Phase 3 (scripts/host-steps/phase3-step2.sh) and the helper uninstalled; listed so the retired path is not mistaken for a live one. |
| `scripts/nmas-tier2-probe:149` | `management_interface` | M | BREAKS | READ | Finds the management interface in `show ip interface brief` by address: an IPv6 management address is never in that table (it is in `show ipv6 interface brief`). Lab probe tool. |
| `scripts/nsot_dedupe_manifest.py:41` | `_groups` | M | unknown | READ | Groups manifest entries by mgmt_ip string: two spellings of one IPv6 address are two groups. One-off maintenance script. |
| `scripts/nsot_reconcile_uids.py:62` | `_reconcile` | M | unknown | READ | Matches manifest mgmt_ip with devices.csv ip by string equality after strip(): right if both hold one spelling; 2001:DB8::10 against 2001:db8::10 misses. Settled by the canonical-form rule; one-off migration script. |
| `app.py:34` | `<file>` | H | works | READ | `import ipaddress` with no use left in app.py: nothing to judge. |
| `lab/clab-sync/clab-startup-sync.sh:404` | `<file>` | D | works | READ | Lab tooling: matches `(ip\|ipv6) address` and drops both families' management-VRF routes. |
| `modules/breakglass_export.py:107` | `list_devices/export_plan/breakglass.describe` | M | works | READ | opaque carrier: the inventory ip copied into the export plan. |
| `modules/config.py:555` | `<file>` | H | works | READ | FLASK_HOST is an opaque string handed to socketio.run; "::" binds both families in Werkzeug. The default 0.0.0.0 is IPv4 only, which does not matter behind the access proxy. |
| `modules/installation_settings.py:452` | `_value/_typed/records_card/_records_drawn/save` | H | works | CHECKED | host kind `[A-Za-z0-9.:_-]+` accepts "::" and 2001:db8::1; url kind `https?://[^\s/]+(/\S*)?` accepts http://[2001:db8::1]:9090. |
| `modules/list_settings.py:252` | `service_identity/group_owner` | H | works | CHECKED | urlsplit strips brackets and ip_address().compressed canonicalises (http://[2001:DB8::0001]:8000 -> 2001:db8::1:8000); unbracketed but used only as an equality key, injective since the port has no colon. |
| `modules/netbox_client.py:1667` | `_parse_ip_brief` | D | works | CHECKED | A v6-only interface shows "unassigned" in show ip interface brief, which the regex accepts, so its state is still read; DEAD CODE, no caller. |
| `modules/nsot/device_ops.py:791` | `may_write` | M | works | READ | Compares the holder's ip with the caller's, both from the same inventory row. |
| `modules/nsot/device_ops.py:829` | `hold_device` | M | works | READ | Opaque carrier of the ip into the hold record; held_by_this_thread likewise. |
| `modules/nsot/golden_state.py:187` | `take` | M | works | READ | Uses hostname, else the ip, as an opaque label. |
| `modules/nsot/golden_state.py:72` | `managed_addresses` | D | works | CHECKED | Counts `ip address` dotted quads and `ipv6 address X/len` (upper-cased), so an IPv6 management interface counts; `link-local` is skipped by design and an `eui-64` line records the prefix (2001:DB8:1::), not the host address. |
| `modules/nsot/golden_state.py:88` | `outside_management` | D | works | CHECKED | (MISSED BY SCAN) Peer upper-cased before lookup; a BGP neighbour 2001:db8::1 matches a managed 2001:DB8::1/64 interface. |
| `modules/nsot/hostvars.py:351` | `<file>` | D | works | READ | Interface schema carries ipv6, ipv6_nd, ospfv3, ripng and dhcpv6_relay beside ipv4, so intent models IPv6 interface addressing. |
| `modules/nsot/intent_edit.py:284` | `<file>` | D | works | READ | ONE_SETTING lists `ip address` and not `ipv6 address`, which is right: IOS IPv6 addresses are additive. |
| `modules/nsot/manifest.py:247` | `inventory_index` | M | works | READ | Keys by the inventory ip string, looked up by the manifest's copy written from the same value (sync_platforms). |
| `modules/nsot/manifest.py:472` | `references` | M | works | READ | Opaque key to credentials.has_device_override. |
| `modules/nsot/migrate.py:105` | `_parse_header` | M | works | CHECKED | `—\s*(.+?)\s*\(([^)]+)\)` returns ("r1", "2001:db8::1"). |
| `modules/nsot/migrate.py:199` | `_group_duplicates` | M | works | READ | Union key f"ip:{addr}" is opaque text; colons inside are harmless. |
| `modules/nsot/parsers/base.py:116` | `_build_handlers` | D | works | CHECKED | `ipv6 unicast-routing` and `ipv6 cef` are flags, `ipv6 router ospf`/`ipv6 router rip` have handlers; `ipv6 access-list` falls to unmodeled and round-trips verbatim. |
| `modules/nsot/parsers/base.py:233` | `BaseParser` | D | works | READ | Interface defaults include ipv6, dhcpv6_relay and ipv6_nd lists. |
| `modules/nsot/parsers/base.py:570` | `_h_static_route` | D | works | READ | `ip route` tagged family ipv4, kept apart from IPv6 routes. |
| `modules/nsot/parsers/base.py:573` | `_h_static_route_v6` | D | works | CHECKED | `ipv6 route ::/0 2001:DB8::FFFF` modelled as {family: ipv6, spec}. |
| `modules/nsot/parsers/base.py:645` | `_interface_child` | D | works | CHECKED | `ipv6 address` kept as a list (2001:DB8::1/64 and FE80::1 link-local both captured); ipv6 nd/ospf/rip/enable and dhcp relay destination modelled. |
| `modules/nsot/parsers/base.py:749` | `_h_bgp` | D | works | READ | Address-family membership preserved, so IPv6 networks/neighbours stay under `address-family ipv6`. |
| `modules/nsot/persist_op.py:279` | `apply` | M | works | READ | Opaque carrier of the inventory ip to the session; plan and row_checks likewise. |
| `modules/nsot/privileged.py:171` | `plan` | M | works | READ | Opaque carrier of the inventory ip to interfaces() (breaks there) and the hash. |
| `modules/nsot/privileged.py:423` | `apply` | M | works | READ | Opaque carrier to device_ops.hold. |
| `modules/nsot/reads.py:380` | `one` | M | works | READ | Opaque carrier of the inventory ip to device_ops.hold and the session. |
| `modules/nsot/repo.py:1061` | `save_golden` | M | works | READ | Opaque carrier into the header and upsert_device. |
| `modules/nsot/repo.py:1993` | `list_goldens` | M | works | READ | Opaque carrier. |
| `modules/nsot/repo.py:516` | `golden_body` | M | works | CHECKED | Header "(mgmt_ip)" round-trips: migrate's `\(([^)]+)\)` returns 2001:db8::1. |
| `modules/nsot/repo.py:62` | `__init__` | M | works | READ | GoldenItem stores mgmt_ip opaquely. |
| `modules/nsot/repo.py:701` | `resolve_identity` | M | works | READ | Opaque carrier to manifest.find_by_ip (spelling caveat there). |
| `modules/nsot/repo.py:979` | `_platforms` | M | works | READ | Keys by the inventory ip string, opaque. |
| `modules/nsot/retire.py:186` | `plan` | M | works | READ | Opaque carrier of the ip/mgmt_ip to host_keys and credentials. |
| `modules/nsot/retire.py:635` | `_address_before` | M | works | READ | Reads mgmt_ip from the manifest JSON, opaque. |
| `modules/nsot/retire.py:941` | `apply` | M | works | READ | Opaque carrier to credentials.clear_device_override, host_keys.forget and delete_device. |
| `modules/nsot/roundtrip.py:58` | `<file>` | D | works | READ | `ipv6 access-list` is order-significant and `ipv6 router` unordered, matching their IPv4 counterparts. |
| `modules/nsot/save_op.py:183` | `_save_one` | M | works | READ | Opaque carrier of the inventory ip to persist_on_device; run and one likewise. |
| `modules/nsot/startup_check.py:55` | `_check_row` | M | works | READ | Opaque carrier of the inventory ip. |
| `modules/nsot/templates/_common.j2:160` | `<file>` | D | works | READ | Renders `ipv6 router ospf` and `ipv6 router rip` blocks from intent. |
| `modules/nsot/templates/_common.j2:242` | `<file>` | D | works | READ | `{{ 'ip' if r.family == 'ipv4' else 'ipv6' }} route {{ r.spec }}` renders IPv6 static routes. |
| `modules/nsot/templates/_common.j2:82` | `<file>` | D | works | READ | ` ip address {{ i.ipv4 }}` renders only the IPv4 field; IPv6 has its own list (line 98). |
| `modules/nsot/templates/_common.j2:98` | `<file>` | D | works | READ | Interface block renders `ipv6 address`, `ipv6 enable`, `ipv6 nd`, `ipv6 ospf`, `ipv6 rip`, `ipv6 dhcp relay destination` from intent; `ipv6 unicast-routing` renders from flags (line 12). |
| `modules/readers/credential_health.py:195` | `tls` | H | works | READ | urlparse().hostname strips the brackets of https://[2001:db8::1]:8006 and create_connection opens AF_INET6. |
| `modules/readonly_commands.py:123` | `_target_args` | D | works | CHECKED | `ping ipv6 2001:db8::1` is allowed (`_TARGET` permits ":"); a target starting "::" or carrying a zone id (fe80::1%Gi1) is refused as not an address. |
| `modules/records_db.py:111` | `connect` | H | works | READ | psycopg host= takes an IPv6 literal; the f"{host}:{port}" in messages is unbracketed text only. |
| `modules/records_db.py:132` | `loopback` | H | works | READ | getaddrinfo then ip_address(a.split("%")[0]).is_loopback, either family (::1 counts). |
| `modules/redact.py:100` | `<file>` | D | works | READ | `snmp-server\s+host\s+\S+` takes any address token, so an IPv6 trap host's community is masked too. |
| `scripts/host-steps/minio-bind.sh:37` | `<file>` | H | works | READ | docker0's IPv4 bridge network is host-internal and independent of the management network's family. |
| `scripts/host-steps/postgres-6a.sh:117` | `<file>` | H | works | READ | 127.0.0.1 loopback (here and in postgres-rotate.sh) exists on an IPv6-only management host. |
| `scripts/nmas-check-secret-storage:153` | `<file>` | D | works | READ | `snmp-server host \S+` takes any address token, IPv6 included. |
| `scripts/nmas-host:73` | `lan_answers` | H | works | READ | socket.create_connection is family-agnostic; lab-host tooling. |
| `scripts/nmas-test:147` | `<file>` | H | works | CHECKED | The confined namespace has ::1 once lo is up (ran `unshare -rn` + `ip -6 addr show lo` + a bind to ::1, 2026-10-17); tests/network_guard.py judges loopback with ipaddress in both families. |
| `telnetlib.py:57` | `open` | H | works | READ | socket.create_connection: family-agnostic. |
| `templates/partials/device_table.html:18` | `<template>` | M | works | READ | Today's (v1) device table puts the address in id attributes (status-<ip>); colons are legal in an id and no script selects it with a CSS selector (searched); retires at cutover. |
## 5. Design (a): ZTP on an IPv6-only management segment

### What is measured already, and what is not

| Fact | Status | Source |
|---|---|---|
| A configless C8000v 17.6 sends IPv6 from its Gi2 MAC at boot: MLDv2, one NS (DAD), and Router Solicitations backing off from 4 s to 242 s | MEASURED (M1, 2026-09-26) | docs/P6_ZTP_PROBE.md, "Observed: M1" |
| The same node starts PnP discovery with no startup config, resolves Cisco's Call Home name and sends a PnP HELLO when it has DNS and a route | MEASURED over IPv4 (M1 re-run, M3) | docs/P6_ZTP.md, D4 |
| With no resolver it broadcasts DNS for `tools.cisco.com` (IPv4) | MEASURED over IPv4 (M3) | docs/P6_ZTP.md, D4 |
| Classic AutoInstall fetches its config by TFTP RRQ, plain RFC 1350, 512-byte blocks | MEASURED over IPv4 (M3) | docs/P6_ZTP.md, D2 |
| The responder's dual-stack socket and `normalise_peer` handle a real IPv6 peer | CODE ONLY: the unit tests use an IPv4 client on a dual-stack listener; no IPv6 peer has ever asked | modules/nsot/ztp_responder.py `normalise_peer`; docs/P6_ZTP_PROBE.md (M4b) |
| Whether the node sends a DHCPv6 SOLICIT at all when no RA has M=1 | UNKNOWN | none |
| Which DUID the node sends (DUID-LL or DUID-LLT; from which interface's MAC: Gi1, Gi2 or the chassis MAC) | UNKNOWN | none |
| Whether the node asks for, and acts on, DHCPv6 option 59 (bootfile URL, RFC 5970) or option 17 (vendor options, Cisco PnP) | UNKNOWN; Cisco documents both for IOS-XE ZTP and PnP over IPv6, which is a vendor's claim, not a measurement here | none in the repository |
| Whether AutoInstall over IPv6 fetches by TFTP, HTTP, or not at all | UNKNOWN | none |

The repository holds no IPv6 measurement of the ZTP path beyond M1's
RS/NS/MLD capture. Every row below that depends on device behaviour is
UNKNOWN until the measurement plan (section 8) runs.

### The identity problem

IPv4 ZTP reserves by MAC: the operator reads the MAC off the box (or the
lab pins it), Kea's `hw-address` reservation matches the DHCPDISCOVER's
`chaddr`, and the responder then trusts the reserved ADDRESS as the
device's identity (P6_ZTP.md D2). DHCPv6 has no `chaddr`. A client
identifies itself by its DUID, and a factory-fresh device's DUID is not on
the box label:

- **DUID-LL (type 3)** is the link-layer address alone, so it is
  predictable from a MAC, but which MAC (the port asking, the lowest
  numbered port, the chassis base MAC) is the platform's choice: UNKNOWN for
  the C8000v until captured.
- **DUID-LLT (type 1)** adds a time, which a configless box with no clock
  invents: not predictable at all.
- **DUID-EN (type 2)** is enterprise number plus an identifier (often the
  serial): predictable only if the serial is known, and C449 records that
  every lab C8000v reports one serial.

Kea gives a way round it that does not need the DUID: a DHCPv6
reservation may be keyed on `hw-address`, and Kea derives the client's MAC
from the packet (`mac-sources`: the DUID if it is type 1 or 3, the
EUI-64 link-local source address on a directly attached link, or the
relay's client-link-layer option 79). M1 measured that the node's
link-local traffic comes from the Gi2 MAC, so on a directly attached
segment Kea can very probably recover the same MAC the IPv4 path
reserves by. "Very probably" is a claim: it holds only if IOS-XE forms
its link-local by EUI-64 (its default) and the SOLICIT leaves from that
address, both measured in step M6-3.

### The options compared

| Path | Identity Mercury trusts | Config transport | New on the host | Phone-home exposure (D4's analogue) | Status |
|---|---|---|---|---|---|
| **A. DHCPv6 stateful (Kea dhcp6) + a reservation keyed by `hw-address` + option 59 `tftp://[addr]/name` (or AutoInstall's TFTP if it follows a v6 server option)** | the reserved address, as IPv4 today; the reservation keyed by the MAC Kea derives | TFTP over IPv6 (the existing responder) | a `subnet6` for the ZTP segment in Kea's dhcp6 config with an include fragment like the IPv4 one; a Router Advertisement on the segment with M=1, the prefix on-link (L=1) and NOT autonomous (A=0), router lifetime 0 | an RA with lifetime 0 gives no default route; withhold option 23 (DNS servers) and 24 (domain list); a check must also refuse RDNSS in any RA on the segment | UNKNOWN: whether the node asks DHCPv6 at all, and whether it honours option 59 |
| B. DHCPv6 reserved by DUID | the reserved address; the reservation keyed by DUID | as A | as A | as A | needs the DUID before the device boots: DUID-LL from a known MAC only if the platform's DUID source is measured; DUID-LLT never |
| C. SLAAC + a DNS or HTTP config fetch | the SLAAC address is derived from the MAC (EUI-64) or random (RFC 7217 / privacy): predictable only for EUI-64; DNS needs a resolver, which D4 forbids | HTTP or TFTP by name | radvd and a resolver on the segment | a resolver on the segment is exactly what D4 forbids | REJECTED on D4: it needs the resolver ZTP must not have |
| D. Cisco PnP over IPv6 (DHCPv6 option 17, enterprise 9, naming a PnP server; or `pnpserver.<domain>` AAAA) | the device's UDI in its PnP HELLO | PnP's own HTTP(S) protocol and a PnP server | a PnP server (a new protocol implementation in the tool, or a third-party package: one of the operator's four stops) | the HELLO carries the UDI; to Mercury only, if the option names Mercury | UNKNOWN; large: a second ZTP protocol beside AutoInstall |
| E. Static IPv6 bootstrap typed on the console | the address typed | none (the operator pastes the bootstrap config) | nothing | none | WORKS today in kind (it is the static path) once section 6's form changes land; it is not zero-touch |

**Recommended: A, with E as the fallback that always exists.** A keeps
every property P.6 earned: the reservation is the authority, the requester's
address selects the device, the filename is the second operand, the
responder renders on request and keeps no copy, and a reservation offers no
route and no resolver. It needs no third-party package beyond what the host
runs (Kea dhcp6 is already running for the lab's host subnets, C701; an RA
can come from a router on the segment). If the RA must come from the NMAS
host itself, `radvd` is a new package and the operator's stop (3). B is
A's fallback keying when step M6-3 shows Kea cannot derive the MAC. D is
the path if M6-4 shows the C8000v's AutoInstall never fetches a config over
IPv6 at all; it is the largest change and is not designed here.

**D4 on IPv6 has three conditions, not two.** IPv4's are "no route or
resolver option" and "nothing answers broadcast DNS". IPv6 adds: **no
Router Advertisement on the ZTP segment carries a non-zero router lifetime
or an RDNSS/DNSSL option**, because a node takes a default route and a
resolver from an RA with no DHCP option at all. The check reads the
segment's RAs (a router's config, or the host's radvd config), not only
Kea's option data. Whether the node, given a route, would phone Cisco over
IPv6 is UNKNOWN (M6-5 measures it on a segment with no way out).

**The measurement that decides between A, B and D** is M6-3 and M6-4 in
section 8: the node's SOLICIT (does it come, from which source address,
with which DUID and option request list, is option 59 or 17 asked for),
then whether it fetches anything when offered option 59.

## 6. Design (b): static IPv6 onboarding

### The form (`templates/v2/_onboard_add.html`, `modules/nsot/onboard.py`)

| Field today | IPv4 meaning | Change |
|---|---|---|
| Management address (`mgmt_ip`) | dotted quad | accept either family; store the compressed lower-case form (RFC 5952) so every string comparison downstream sees one spelling |
| Mask (`mgmt_mask`) | dotted mask | becomes **Prefix length**, accepting `/24`-style for IPv4 too; a dotted mask still accepted for IPv4 and converted; for IPv6 a dotted mask is refused naming both operands ("2001:db8::10 is IPv6; 255.255.255.0 is an IPv4 mask"). Better still, one field `address/prefix` (`2001:db8:0:1::10/64`), parsed by `ipaddress.ip_interface` |
| Gateway (`manager_gateway`) | IPv4 next hop | either family, same family as the address; a link-local gateway (`fe80::1`) is legal for IPv6 and needs the interface (`ipv6 route ::/0 GigabitEthernet2 FE80::1`) |
| Management interface | unchanged | unchanged |
| Domain | `ip domain name` (SSH keys) | unchanged; the same command on IOS and IOS-XE |
| MAC (DHCP, ZTP) | `hw-address` | unchanged for ZTP path A; DHCP's reservation may be by DUID (the DHCP page already takes DUID for host reservations) |

The page's placeholders stay in the documentation ranges (192.0.2.10,
2001:db8::10). Inference of the family from the address, never a second
"family" selector (the safe path must not be tedious).

### What the bootstrap config renders

For `2001:db8:0:1::10/64` on `GigabitEthernet2` with gateway `2001:db8:0:1::1`:

```
ipv6 unicast-routing            ! only if the device ROUTES; a host-only management needs none
interface GigabitEthernet2
 ipv6 address 2001:DB8:0:1::10/64
 ipv6 enable
 no shutdown
ipv6 route ::/0 2001:DB8:0:1::1   ! a router; a switch's management uses the same form on IOS-XE
ip domain name example.net
ip ssh version 2
```

Three things the renderer must know that IPv4 did not need:
1. **A routing device ignores RAs for its own default route** once
   `ipv6 unicast-routing` is on, so the static default is required when a
   gateway is given; a vIOS L2 switch (no `ipv6 unicast-routing`) may take
   an RA's default instead, which is the D4 hazard again: render the static
   route always.
2. **`ipv6 address` lines are additive.** Re-applying the bootstrap with a
   different address ADDS a second one; merge-only deploy (CLAUDE.md) keeps
   both. Changing a device's management IPv6 address is a "path to the
   device" change (repair route rule) and a Mode B removal of the old line.
3. **IOS prints IPv6 addresses upper case** (`2001:DB8::10`), in
   running-config and in `show` output, where NetBox, Kea and Python's
   `ipaddress` print lower case. Every comparison of an address read from a
   device with one held by Mercury compares parsed `ip_address` objects,
   never strings. This one rule closes most of the "string equality" sites in
   the table.

### Verify's reachability and SSH over IPv6

- **SSH** (Netmiko/Paramiko): an IPv6 literal as `host` works in Paramiko
  (it resolves by `getaddrinfo`); a link-local needs `%zone`, which Mercury
  should refuse as a management address (a zone is a property of the
  manager's interface, not of the device). Known-hosts keys for an IPv6
  host are written `[2001:db8::10]:22` only when the port is not 22, and
  bare otherwise; Mercury's own store (`modules/host_keys.py`) keys by
  device name or address: see the site table for which.
- **Reachability**: the online check's ICMP must use the family of the
  address (`ping -6`, or `ping` on a modern iputils which picks the family
  from the literal; UNKNOWN on the host's iputils until read), and TCP/22
  by `socket.create_connection`, which is family-agnostic.
- **Verify's management sections** (QUICK scope) must count `ipv6 address`,
  `ipv6 route` and `ipv6 access-list` on vty as management, or a change to
  the IPv6 management path is verified at the wrong depth.

### NetBox records

- The device's management address is `primary_ip6` when it is IPv6, and
  Mercury reads `primary_ip4 or primary_ip6` (or NetBox's computed
  `primary_ip`, which follows `PREFER_IPV4`, C560) only through one
  resolver, never two.
- An `ipam/ip-addresses` record for `2001:db8:0:1::10/64` assigned to the
  management interface, its `/64` prefix created or found, and the
  provenance recorded as for IPv4.
- C560 is the warning: this lab's NetBox already prefers IPv6 for
  `primary_ip` unless `PREFER_IPV4` is set, so a reader of `primary_ip`
  silently changes family when a device gains an IPv6 address.

## 7. Design (c): Mercury's own host networking

| Piece | IPv4 today | IPv6 needs | Verdict |
|---|---|---|---|
| ZTP responder socket (`deploy/systemd/nmas-ztp-responder.socket`) | `ListenDatagram=69`, bound to the ZTP interface | already dual-stack (`[::]:69`, measured M4b) | works |
| ZTP responder service sandbox (`deploy/systemd/nmas-ztp-responder.service:25`) | `RestrictAddressFamilies=AF_INET AF_UNIX` | `AF_INET6` added: the TFTP reply goes from a NEW socket of the peer's family (`ztp_responder.py:260`), so an IPv6 peer's reply socket is refused by the seccomp filter and the device hears silence (M4b's failure, in the other family) | BREAKS (READ) |
| The responder run by hand (`scripts/nmas-ztp-responder:54-56`) | `--listen host:port`, `rpartition(":")`, AF_INET | parse `[addr]:port`, socket of the address's family | BREAKS (READ); a test and probe path only |
| TFTP once (`scripts/nmas-tftp-once:66-69`) | AF_INET6, `IPV6_V6ONLY=0`, `::` | nothing | works (READ) |
| The ZTP segment's own IPv6 address on the NMAS host | the derived interface address (D3) | a global or ULA address on the ZTP interface, derived the same way (the interface's address in the subnet6 Kea serves), never a link-local (option 59 carries a URL a node must reach without a zone) | UNKNOWN: whether the ZTP interface holds an IPv6 address today (one read-only `ip -6 addr show` on the NMAS host) |
| ufw for udp/69 | `allow in on <if> proto udp from <v4 subnet>` | the same rule for the v6 subnet; ufw keeps separate v4 and v6 rule sets | UNKNOWN (one read-only `ufw status` on the host) |
| Kea dhcp6 listening on the ZTP interface | dhcp4 listens there | dhcp6's `interfaces-config` must include the ZTP interface | UNKNOWN (read-only `kea-dhcp6` config read) |
| Syslog input (`deploy/rsyslog/10-network-devices.conf`) | `imudp` port 514, no address | rsyslog's imudp listens on both families by default; files are named `/var/log/network/<source-ip>.log` (colons are legal in a Linux file name); Alloy labels by the hostname in the line, not the file name | works (READ); one measured line from an IPv6 source confirms |
| SNMP traps (snmptrapd) | `udp:162` | `udp6:162` must be in snmptrapd's agent address list | UNKNOWN (host config outside the repository) |
| Prometheus exporters (snmp, blackbox) | `target=<v4>` | a target parameter of `2001:db8::10` works for snmp_exporter only as `udp6:[2001:db8::10]` or `[2001:db8::10]`; blackbox ICMP needs `preferred_ip_protocol: ip6` (its default is ip6 with fallback) | see the site table (prometheus_targets) |
| The app's bind (`modules/config.py:555`) | `0.0.0.0` | not needed for devices (the app is reached through the access proxy); `::` works in Werkzeug; the printed URL `app.py:616` writes `http://:::5000` | cosmetic BREAK |
| The confined test namespace (`scripts/nmas-test`) | `unshare -rn`, `ip link set lo up` | `::1` exists in it (CHECKED 2026-10-17: `ip -6 addr show lo` in a fresh `unshare -rn` shows `::1/128`, and a socket binds `::1`); `tests/network_guard.py` judges loopback with `ipaddress.ip_address(host).is_loopback` in both families and probes `2001:db8::1` | works (CHECKED) |
## 8. Measurement plan: an IPv6-only management throwaway

On the lab's throwaway C8000v (`docs/bootstrap-probe/nmas-throwaway.clab.yml`,
runbook `docs/THROWAWAY_SESSION.md`), in its own lab and its own list
(`throwaway`). **Never on s3; nothing between 08:30 and 09:10 UTC (02:30 to
03:10 the operator's UTC−6).** A configless boot is a restart of a node:
declare a planned-restart window first (`POST /restarts/planned`). Every
read of the device goes through Mercury once it is reachable; before that,
the evidence is a packet capture on the lab host's bridge (read-only) and
Kea's own logs and lease file.

### The topology change

A copy of the throwaway topology, `nmas-throwaway-v6.clab.yml`, differing in
four things:

1. The ZTP link stays `tw-ztp-a:Gi2` to `br-mgmt` with its pinned MAC
   (`aa:bb:cc:00:02:60`-style, a value chosen free and recorded, as the IPv4
   session did).
2. **No IPv4 on the ZTP segment for this node:** no `subnet4` reservation for
   the MAC, and the node's Gi2 never offered an IPv4 lease (Kea subnet 255's
   pool stays pool-less, as today). Gi1 stays vrnetlab's
   (`CLAB_MGMT_PASSTHROUGH`, unanswered, as M2d measured), so the only
   management path is IPv6 on Gi2.
3. A **subnet6 for the ZTP segment** (a documentation-style ULA or a prefix
   from the lab's plan, recorded in the topology header and checked free in
   Kea and the goldens the way the IPv4 session checked .60), served on the
   NMAS host's ZTP interface, with the NMAS host holding an address in it.
4. **An RA source on the segment** with M=1, the prefix on-link (L=1) and
   not autonomous (A=0), router lifetime 0, no RDNSS: `tw-frr` can send it
   (FRR's `ipv6 nd` commands, already on the lab host's image; no new
   package), which keeps radvd off the NMAS host. `tw-frr` also takes an
   IPv6 address for C117's BGP loop (an IPv6 session over IPv6 transport).

### What is measured, in order, and what each decides

| # | Measurement | How (read-only unless named) | Decides |
|---|---|---|---|
| M6-0 | The host side exists: the NMAS host's ZTP interface holds an IPv6 address in the subnet6; Kea dhcp6 listens on that interface; ufw admits udp/69 over IPv6 from the subnet; snmptrapd listens on `udp6`; rsyslog's imudp is bound on `::` | `nmas-host nmas -- ip -6 addr show`, `ss -lun`, `ufw status` (counts and names, never values) | Whether section 7's UNKNOWN rows are host work before anything boots |
| M6-1 | A configless boot, nothing offered: what the node sends over IPv6 in its first 10 minutes (RS, NS, MLD, SOLICIT, DNS, PnP) | capture on the lab host's bridge port, filtered to the pinned MAC | Whether the node tries DHCPv6 with no RA telling it to (M flag), and whether it phones Cisco with no route |
| M6-2 | The same with the RA (M=1, lifetime 0) | the same capture | Whether an M=1 RA starts DHCPv6; whether lifetime 0 keeps it from a default route (`show ipv6 route` once reachable) |
| M6-3 | The SOLICIT's contents | the capture: source address (EUI-64 of the Gi2 MAC or not), the DUID type and its link-layer address, the option request list (is 59 asked? 17? 23?) | **A against B**: if the source is EUI-64 of the pinned MAC or the DUID is DUID-LL of it, a `hw-address` reservation works (A); if the DUID uses another MAC, reserve by DUID-LL of THAT MAC (B), and record which MAC as a platform fact |
| M6-4 | Offered option 59 `tftp://[<host address>]/<name>.cfg`: does the node fetch, by which protocol, which name | the responder's reveal row and its journal; the capture | **A against D**: a fetch means AutoInstall works over IPv6 with Mercury's responder unchanged except the systemd family line; no fetch with 59 asked means try option 17 (PnP) as the next session's question |
| M6-5 | With a route and a resolver deliberately ABSENT, does the node still try to reach Cisco over IPv6 (AAAA queries to a multicast or anycast resolver, PnP HELLO) | the capture | D4's IPv6 conditions: what the job-health check must refuse on the segment |
| M6-6 | Phase 2 over IPv6: SSH with the staged credential, the seven steps, NetBox's record (`primary_ip6`), the device page | Mercury's own screens and records | That the static/ZTP common path (SSH, persist, NetBox, monitoring) holds end to end; each failure is a site in the table found in practice |
| M6-7 | Monitoring over IPv6: the snmp_exporter target, the blackbox probe, the `instance` label, the heartbeat from syslog over IPv6, a trap | Prometheus's targets page and Loki, read-only through `nmas-host` | The monitoring, logs and silences rows of section 3, and three UNKNOWNs: (1) whether the installed snmp_exporter scrapes a bare IPv6 file_sd target (`prometheus_targets.py:142`) or needs `[addr]` / `udp6:[addr]`; (2) the text of one IPv6 BGP peer's `cbgpPeer2RemoteAddr` label (`neighbours.py:329`, `routing-modules.yml:10`); (3) the trap `device` label for a trap from an IPv6 source (`c722-device-label.sh:45`, `ibn7-severity-trap-label.sh:88`) |
| M6-8 | Deploy, verify (a BGP change to `tw-frr` over IPv6 transport), forced rollback, retry, restore, rotation and persist, retire | the session's Parts 5 to 8, run on IPv6 | deploy/verify/rollback, rotation, adopt-free retire over IPv6 |
| M6-9 | Static onboarding: the same node configless again (a CONTAINER start, which clears it), the static bootstrap from section 6 pasted on the console | the bootstrap Mercury renders, applied the way the static path applies it today, then Mercury | The static path on IPv6 alone, and that E is always available |

Each measurement's result is a line in the register or this document,
dated, with the capture's file named on the lab host; no address values
in the repository.

## 9. Register shape

One FUTURE epic, Phase 8's first, registered as **C1245** in
`docs/OPEN_FINDINGS.md`. Its children below become register rows of their
own when the operator moves the epic to active, so each can close on its own
measured run. The charter bucket for all of them is FUTURE, and nothing is
active until then.

| Row | Bucket | Title | Closes when |
|---|---|---|---|
| E-IPv6 | FUTURE (Phase 8, first) | **IPv6 parity: every feature works on an IPv6-only management network** (the operator, 2026-10-17; docs/IPV6_PARITY.md: 371 sites, 109 break, 9 unknown) | every child is closed and the IPv6 throwaway (section 8) runs M6-6 to M6-9 green |
| E-IPv6.0 | FUTURE | Addresses are canonical at entry and compared as parsed objects (the cross-cutting text-equality class, about 40 sites) | a scan finds no `==` between address strings from two sources; planted control |
| E-IPv6.1 | FUTURE | Static onboarding: the form's prefix length, validation, the bootstrap's `ipv6 address` and `ipv6 route`, the family-aware ICMP probe | M6-9 |
| E-IPv6.2 | FUTURE | ZTP over DHCPv6 (design A; B or D by measurement), D4's IPv6 conditions, the responder unit's AF_INET6 | M6-1 to M6-4 decide the design, then a ZTP run on IPv6 |
| E-IPv6.3 | FUTURE | Deploy, verify and rollback: additive `ipv6 address` keys and rollback, parsed read-back, IPv6 route retention, IPv6 attachments for blast radius, expected effects and Mode B's management interface | M6-8 |
| E-IPv6.4 | FUTURE | Monitoring, silences and logs: file_sd target form, the host:port helper, the silence and acknowledgement matchers, `logging host ipv6`, IP SLA targets, Drained | M6-7 |
| E-IPv6.5 | FUTURE | Path trace over IPv6 (`show ipv6 cef`) | a trace across an IPv6-only lab path |
| E-IPv6.6 | FUTURE | NetBox: the management address as `primary_ip6`, the inventory's family, the tab, `ipv6 route` | M6-6's NetBox record read back |
| E-IPv6.7 | FUTURE | DHCP leftovers: prefix-form pools in `span()`, the one-off Kea tools on a single family, `ipv6 address dhcp` | the DHCP page edits a v6-only Kea |
| E-IPv6.8 | FUTURE | Mercury's host: the ZTP interface's IPv6 address, ufw, Kea dhcp6 interfaces, snmptrapd `udp6`, the trusted-peer comparison, the bind default and URL | M6-0 |

Already registered and part of this epic: C554 (Mode B and `ipv6 access-list`),
C560 (NetBox `primary_ip` preferring IPv6), C681 and C697 (DHCPv6 leases on
lab hosts).
