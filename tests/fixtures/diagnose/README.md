# The diagnosis runbooks' captures (H18; C2414, C2415, C2681, C2695)

Real device output for the reads the diagnosis runbooks send (docs/HEAL_TO_INTENT.md 19.3,
"What a Diagnose… run reads"), captured read-only on 2026-11-07 between 20:33 and 20:51 UTC
from the home lab, through Mercury's own reads engine on the NMAS host (`reads.run`, kind
`agent`, the Default network), each answer masked by the engine before it was kept. r2 and r4
are IOS-XE (C8000v); s1 is IOS (vIOS-L2). Never s3, never a CU lab device. Each run is on the
host's History › Reads under its id.

One file per device and command, `<host>__<command slug>.txt`, byte for byte as the engine
recorded it. Two commands share a slug's shape, so two files are named by what they ask:
`r2__show_ipv6_route_unspecified.txt` is `show ipv6 route ::` and
`…__show_ipv6_route_default_prefix.txt` is `show ipv6 route ::/0`. Most commands were sent with
the addresses upper case, as the device prints them; the runbooks render an IPv6 address in
Python's form (lower case), which r4 answered the same (its two lower-case captures), and the
tests key a capture by the rendered command: the answer is the device's.

**Edits (the documentation range, for the publication scan):** `s1__show_ip_arp.txt`, the two
management-segment lines, their lab addresses written as 192.0.2.2 and 192.0.2.18 (columns
kept); `r4__show_ip_access_lists_NAT_PRIVATE.txt`, entry 10, the private /8 it permits written
as `192.0.2.0, wildcard bits 0.0.0.255`. Nothing else is edited.

## What was measured with them

- **`show ip route <address>` never matches the default route** on either platform: r2 prints
  `% Network not in table` for 198.51.100.1 and s1 `% Subnet not in table` for 10.255.1.14,
  while each one's CEF forwards both by 0.0.0.0/0. `show ip route 0.0.0.0` reads the default
  (`Routing entry for 0.0.0.0/0, supernet`). **`show ipv6 route <address>` does match it** (s1,
  `Routing entry for ::/0`), and `show ipv6 route ::` is not the default but `::/127`.
- **IPv6 CEF names link-local next hops** (`nexthop FE80::… GigabitEthernet2`), which no intent
  holds; `show ospfv3 neighbor detail` (IOS-XE) names each neighbour's link-local address
  beside its router id. A discard route prints `attached to Null0` (r4, 2001:DB8::/32).
- **vIOS-L2 refuses the bounded traceroute:** `traceroute <a> numeric timeout 2 probe 1 ttl 1
  16` and the same without `numeric` print IOS's invalid-input marker at the first option, for
  IPv4 and IPv6. A plain `traceroute <a>` answers (three probes a hop).
- **vIOS-L2 refuses `show ipv6 neighbors <address>`**; `show ipv6 neighbors <interface>`
  answers on both platforms.
- **The lab's IPv6 is not whole:** r2 does not reach s1's 2001:DB8:1::21 (`XXXXX`; r2's CEF
  takes 2001:DB8::/32 to r3 and r4, and r4 discards it at Null0), and s1 does not reach r4's
  2001:DB8:1::14 (`.....`), while both reach by IPv4.
- **No access list on these devices printed a match count**, so the counters' shape is not
  captured.

## The captures

| File | Device | Command | UTC | Reads run |
|---|---|---|---|---|
| r2__ping_10.255.1.14_source_Loopback0_repeat_5_timeout_2.txt | r2 | `ping 10.255.1.14 source Loopback0 repeat 5 timeout 2` | 2026-11-07T20:35Z | 20261107T203522323880Z-3d90c6fd |
| r2__ping_10.255.1.21_source_Loopback0_repeat_5_timeout_2.txt | r2 | `ping 10.255.1.21 source Loopback0 repeat 5 timeout 2` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__ping_10.255.3.14_size_1500_df_bit_repeat_2_timeout_2.txt | r2 | `ping 10.255.3.14 size 1500 df-bit repeat 2 timeout 2` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__ping_10.255.3.14_source_GigabitEthernet2_repeat_5_timeout_2.txt | r2 | `ping 10.255.3.14 source GigabitEthernet2 repeat 5 timeout 2` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__ping_10.255.3.99_repeat_5_timeout_2.txt | r2 | `ping 10.255.3.99 repeat 5 timeout 2` | 2026-11-07T20:35Z | 20261107T203522323880Z-3d90c6fd |
| r2__ping_ipv6_2001_DB8_1_14_source_Loopback0_repeat_5_timeout_2.txt | r2 | `ping ipv6 2001:DB8:1::14 source Loopback0 repeat 5 timeout 2` | 2026-11-07T20:35Z | 20261107T203522323880Z-3d90c6fd |
| r2__ping_ipv6_2001_DB8_1_21_source_Loopback0_repeat_5_timeout_2.txt | r2 | `ping ipv6 2001:DB8:1::21 source Loopback0 repeat 5 timeout 2` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__ping_ipv6_2001_DB8_3_99_repeat_5_timeout_2.txt | r2 | `ping ipv6 2001:DB8:3::99 repeat 5 timeout 2` | 2026-11-07T20:35Z | 20261107T203522323880Z-3d90c6fd |
| r2__show_interfaces_GigabitEthernet2.txt | r2 | `show interfaces GigabitEthernet2` | 2026-11-07T20:35Z | 20261107T203557841196Z-2b27cef1 |
| r2__show_ip_access_lists_meraki_fqdn_dns.txt | r2 | `show ip access-lists meraki-fqdn-dns` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__show_ip_cef_10.255.1.21.txt | r2 | `show ip cef 10.255.1.21` | 2026-11-07T20:33Z | 20261107T203316551852Z-4334740c |
| r2__show_ip_cef_198.51.100.1.txt | r2 | `show ip cef 198.51.100.1` | 2026-11-07T20:35Z | 20261107T203459259479Z-61250b9e |
| r2__show_ip_ospf_interface_GigabitEthernet2.txt | r2 | `show ip ospf interface GigabitEthernet2` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__show_ip_route_0.0.0.0.txt | r2 | `show ip route 0.0.0.0` | 2026-11-07T20:35Z | 20261107T203459259479Z-61250b9e |
| r2__show_ip_route_10.255.1.14.txt | r2 | `show ip route 10.255.1.14` | 2026-11-07T20:33Z | 20261107T203316551852Z-4334740c |
| r2__show_ip_route_10.255.1.21.txt | r2 | `show ip route 10.255.1.21` | 2026-11-07T20:33Z | 20261107T203316551852Z-4334740c |
| r2__show_ip_route_10.255.3.14.txt | r2 | `show ip route 10.255.3.14` | 2026-11-07T20:35Z | 20261107T203459259479Z-61250b9e |
| r2__show_ip_route_198.51.100.1.txt | r2 | `show ip route 198.51.100.1` | 2026-11-07T20:35Z | 20261107T203459259479Z-61250b9e |
| r2__show_ipv6_cef_2001_DB8_1_12.txt | r2 | `show ipv6 cef 2001:DB8:1::12` | 2026-11-07T20:35Z | 20261107T203459259479Z-61250b9e |
| r2__show_ipv6_cef_2001_DB8_1_14.txt | r2 | `show ipv6 cef 2001:DB8:1::14` | 2026-11-07T20:33Z | 20261107T203316551852Z-4334740c |
| r2__show_ipv6_cef_2001_DB8_1_21.txt | r2 | `show ipv6 cef 2001:DB8:1::21` | 2026-11-07T20:35Z | 20261107T203459259479Z-61250b9e |
| r2__show_ipv6_cef_2001_DB8_FFFF_1.txt | r2 | `show ipv6 cef 2001:DB8:FFFF::1` | 2026-11-07T20:35Z | 20261107T203459259479Z-61250b9e |
| r2__show_ipv6_interface_GigabitEthernet2.txt | r2 | `show ipv6 interface GigabitEthernet2` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__show_ipv6_neighbors_FE80_A8C1_ABFF_FE7B_A0DB.txt | r2 | `show ipv6 neighbors FE80::A8C1:ABFF:FE7B:A0DB` | 2026-11-07T20:35Z | 20261107T203502943450Z-9118167f |
| r2__show_ipv6_neighbors_GigabitEthernet2.txt | r2 | `show ipv6 neighbors GigabitEthernet2` | 2026-11-07T20:35Z | 20261107T203502943450Z-9118167f |
| r2__show_ipv6_ospf_interface_GigabitEthernet2.txt | r2 | `show ipv6 ospf interface GigabitEthernet2` | 2026-11-07T20:36Z | 20261107T203557841196Z-2b27cef1 |
| r2__show_ipv6_route_2001_DB8_1_14.txt | r2 | `show ipv6 route 2001:DB8:1::14` | 2026-11-07T20:33Z | 20261107T203316551852Z-4334740c |
| r2__show_ipv6_route_2001_DB8_3_14.txt | r2 | `show ipv6 route 2001:DB8:3::14` | 2026-11-07T20:35Z | 20261107T203502943450Z-9118167f |
| r2__show_ipv6_route_2001_DB8_FFFF_1.txt | r2 | `show ipv6 route 2001:DB8:FFFF::1` | 2026-11-07T20:35Z | 20261107T203502943450Z-9118167f |
| r2__show_ipv6_route_default_prefix.txt | r2 | `show ipv6 route ::/0` | 2026-11-07T20:35Z | 20261107T203522323880Z-3d90c6fd |
| r2__show_ipv6_route_unspecified.txt | r2 | `show ipv6 route ::` | 2026-11-07T20:35Z | 20261107T203502943450Z-9118167f |
| r2__show_ospfv3_neighbor_detail.txt | r2 | `show ospfv3 neighbor detail` | 2026-11-07T20:35Z | 20261107T203502943450Z-9118167f |
| r2__traceroute_10.255.1.21_numeric_timeout_2_probe_1_ttl_1_16.txt | r2 | `traceroute 10.255.1.21 numeric timeout 2 probe 1 ttl 1 16` | 2026-11-07T20:35Z | 20261107T203522323880Z-3d90c6fd |
| r2__traceroute_ipv6_2001_DB8_1_21_numeric_timeout_2_probe_1_ttl_1_16.txt | r2 | `traceroute ipv6 2001:DB8:1::21 numeric timeout 2 probe 1 ttl 1 16` | 2026-11-07T20:35Z | 20261107T203522323880Z-3d90c6fd |
| r4__show_ip_access_lists_NAT_PRIVATE.txt | r4 | `show ip access-lists NAT-PRIVATE` | 2026-11-07T20:37Z | 20261107T203738396213Z-ca7aaae4 |
| r4__show_ip_cef_10.255.1.21.txt | r4 | `show ip cef 10.255.1.21` | 2026-11-07T20:36Z | 20261107T203603517658Z-da1654bd |
| r4__show_ip_route_10.255.1.12.txt | r4 | `show ip route 10.255.1.12` | 2026-11-07T20:37Z | 20261107T203738396213Z-ca7aaae4 |
| r4__show_ip_route_10.255.1.21.txt | r4 | `show ip route 10.255.1.21` | 2026-11-07T20:36Z | 20261107T203603517658Z-da1654bd |
| r4__show_ipv6_cef_2001_DB8_1_12.txt | r4 | `show ipv6 cef 2001:DB8:1::12` | 2026-11-07T20:36Z | 20261107T203603517658Z-da1654bd |
| r4__show_ipv6_cef_2001_DB8_1_21.txt | r4 | `show ipv6 cef 2001:DB8:1::21` | 2026-11-07T20:36Z | 20261107T203603517658Z-da1654bd |
| r4__show_ipv6_route_2001_DB8_1_12.txt | r4 | `show ipv6 route 2001:DB8:1::12` | 2026-11-07T20:37Z | 20261107T203738396213Z-ca7aaae4 |
| r4__show_ipv6_route_2001_DB8_1_21.txt | r4 | `show ipv6 route 2001:DB8:1::21` | 2026-11-07T20:36Z | 20261107T203603517658Z-da1654bd |
| r4__show_ip_arp_10.255.3.11.txt | r4 | `show ip arp 10.255.3.11` | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_ip_arp_10.255.3.12.txt | r4 | `show ip arp 10.255.3.12` | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_interfaces_GigabitEthernet3.txt | r4 | `show interfaces GigabitEthernet3` | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_ip_interface_GigabitEthernet3.txt | r4 | `show ip interface GigabitEthernet3` | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_ip_route_10.255.1.11.txt | r4 | `show ip route 10.255.1.11` | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_ip_cef_10.255.1.11.txt | r4 | `show ip cef 10.255.1.11` | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_ipv6_neighbors_fe80_a8c1_abff_feea_39ae.txt | r4 | `show ipv6 neighbors fe80::a8c1:abff:feea:39ae` (the rendered, lower-case form: answered) | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_ipv6_interface_GigabitEthernet3.txt | r4 | `show ipv6 interface GigabitEthernet3` | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| r4__show_ipv6_cef_2001_db8_1_12.txt | r4 | `show ipv6 cef 2001:db8:1::12` (lower case: answered) | 2026-11-07T20:51Z | 20261107T205112942292Z-5d98ce7d |
| s1__ping_10.10.10.3_source_Loopback0_repeat_5_timeout_2.txt | s1 | `ping 10.10.10.3 source Loopback0 repeat 5 timeout 2` | 2026-11-07T20:44Z | 20261107T204417834229Z-8ccc8081 |
| s1__ping_10.255.1.14_source_Loopback0_repeat_5_timeout_2.txt | s1 | `ping 10.255.1.14 source Loopback0 repeat 5 timeout 2` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__ping_ipv6_2001_DB8_1_14_source_Loopback0_repeat_5_timeout_2.txt | s1 | `ping ipv6 2001:DB8:1::14 source Loopback0 repeat 5 timeout 2` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__show_interfaces_GigabitEthernet0_2.txt | s1 | `show interfaces GigabitEthernet0/2` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_interfaces_Vlan10.txt | s1 | `show interfaces Vlan10` | 2026-11-07T20:44Z | 20261107T204417834229Z-8ccc8081 |
| s1__show_ip_access_lists_CISCO_CWA_URL_REDIRECT_ACL.txt | s1 | `show ip access-lists CISCO-CWA-URL-REDIRECT-ACL` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_ip_arp.txt | s1 | `show ip arp` (two lines edited, above) | 2026-11-07T20:37Z | 20261107T203728162183Z-2a62fb41 |
| s1__show_ip_arp_10.10.10.3.txt | s1 | `show ip arp 10.10.10.3` | 2026-11-07T20:44Z | 20261107T204417834229Z-8ccc8081 |
| s1__show_ip_cef_10.10.10.3.txt | s1 | `show ip cef 10.10.10.3` | 2026-11-07T20:44Z | 20261107T204417834229Z-8ccc8081 |
| s1__show_ip_cef_10.255.1.14.txt | s1 | `show ip cef 10.255.1.14` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__show_ip_interface_GigabitEthernet0_2.txt | s1 | `show ip interface GigabitEthernet0/2` | 2026-11-07T20:44Z | 20261107T204417834229Z-8ccc8081 |
| s1__show_ip_interface_Vlan10.txt | s1 | `show ip interface Vlan10` | 2026-11-07T20:44Z | 20261107T204417834229Z-8ccc8081 |
| s1__show_ip_ospf_interface_GigabitEthernet0_2.txt | s1 | `show ip ospf interface GigabitEthernet0/2` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_ip_route_0.0.0.0.txt | s1 | `show ip route 0.0.0.0` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__show_ip_route_10.10.10.3.txt | s1 | `show ip route 10.10.10.3` | 2026-11-07T20:44Z | 20261107T204417834229Z-8ccc8081 |
| s1__show_ip_route_10.10.10.5.txt | s1 | `show ip route 10.10.10.5` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_ip_route_10.255.1.14.txt | s1 | `show ip route 10.255.1.14` | 2026-11-07T20:33Z | 20261107T203319786668Z-04d7d535 |
| s1__show_ipv6_access_list_preauth_ipv6_acl.txt | s1 | `show ipv6 access-list preauth_ipv6_acl` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_ipv6_cef_2001_DB8_1_14.txt | s1 | `show ipv6 cef 2001:DB8:1::14` | 2026-11-07T20:33Z | 20261107T203319786668Z-04d7d535 |
| s1__show_ipv6_interface_GigabitEthernet0_2.txt | s1 | `show ipv6 interface GigabitEthernet0/2` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_ipv6_neighbors_FE80_A8C1_ABFF_FE93_3623.txt | s1 | `show ipv6 neighbors FE80::A8C1:ABFF:FE93:3623` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__show_ipv6_neighbors_GigabitEthernet0_2.txt | s1 | `show ipv6 neighbors GigabitEthernet0/2` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__show_ipv6_ospf_interface_GigabitEthernet0_2.txt | s1 | `show ipv6 ospf interface GigabitEthernet0/2` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_ipv6_route_2001_DB8_1_14.txt | s1 | `show ipv6 route 2001:DB8:1::14` | 2026-11-07T20:33Z | 20261107T203319786668Z-04d7d535 |
| s1__show_ipv6_route_default_prefix.txt | s1 | `show ipv6 route ::/0` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__show_mac_address_table_address_0c00.6f31.800a.txt | s1 | `show mac address-table address 0c00.6f31.800a` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__show_mac_address_table_dynamic.txt | s1 | `show mac address-table dynamic` | 2026-11-07T20:33Z | 20261107T203319786668Z-04d7d535 |
| s1__show_spanning_tree_interface_GigabitEthernet0_3.txt | s1 | `show spanning-tree interface GigabitEthernet0/3` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__traceroute_10.255.1.14.txt | s1 | `traceroute 10.255.1.14` | 2026-11-07T20:37Z | 20261107T203728162183Z-2a62fb41 |
| s1__traceroute_10.255.1.14_numeric_timeout_2_probe_1_ttl_1_16.txt | s1 | `traceroute 10.255.1.14 numeric timeout 2 probe 1 ttl 1 16` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__traceroute_10.255.1.14_timeout_2_probe_1_ttl_1_16.txt | s1 | `traceroute 10.255.1.14 timeout 2 probe 1 ttl 1 16` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |
| s1__traceroute_ipv6_2001_DB8_1_14_numeric_timeout_2_probe_1_ttl_1_16.txt | s1 | `traceroute ipv6 2001:DB8:1::14 numeric timeout 2 probe 1 ttl 1 16` | 2026-11-07T20:36Z | 20261107T203619928412Z-2a4f824f |
| s1__traceroute_ipv6_2001_DB8_1_14_timeout_2_probe_1_ttl_1_16.txt | s1 | `traceroute ipv6 2001:DB8:1::14 timeout 2 probe 1 ttl 1 16` | 2026-11-07T20:37Z | 20261107T203702978918Z-7e1d5ddf |

## Loki (C2695)

Read 2026-11-07 ~20:40 UTC from the lab's Loki through Mercury's own `LokiIntegration` and
`device_logs.selector` (the device's label), each line masked by `redact_text`, kept in Loki's
answer shape (`tests/fixtures/loki/lines_r4.json`'s):

- `loki_updown_r4.json`: r4's UPDOWN lines, 18:00 to 18:15 UTC (the operator's bounce of
  GigabitEthernet4, 18:05 to 18:08): `%LINEPROTO-5-UPDOWN` down and up twice and
  `%LINK-3-UPDOWN` up twice, as Loki stores them, by severity stream;
- `loki_gigabitethernet4_r4.json`: every r4 line naming GigabitEthernet4, 18:05 to 18:09 UTC:
  the same lines with OSPF's and OSPFv3's ADJCHG between them (OSPFv3's in a stream with no
  severity label).

The shutdown printed no `%LINK-5-CHANGED ... administratively down` line in Loki, and no
`%LINK-3-UPDOWN ... down`. s1's window (GigabitEthernet1/1, 18:09 to 18:13 UTC) holds no
UPDOWN line at all: its lines there are the configuration and rollback timer's own.
