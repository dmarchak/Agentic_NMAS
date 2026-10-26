# Endpoint layer fixtures

Real captures, read on 2026-10-26 08:24 UTC through Mercury's own read path (the stored
credential, `open_ssh`, allowlisted show commands only) from the lab's s1 (vIOS-L2, `cisco_ios`)
and r1 (C8000v, `cisco_iosxe`): `show mac address-table dynamic`, `show ip arp` and
`show ipv6 neighbors`, one file each, named `<device>__<command>.txt`.

One edit: the two addresses on the operator's LAN (s1's management neighbours) are mapped into
192.0.2.0/24 (to 192.0.2.2 and 192.0.2.18, the last octet kept); the lab's own 10.10 and 10.255
addresses are kept, as other fixtures keep them.

What they show, as read: s1's MAC table held five entries, all learned on its trunk to s2
(GigabitEthernet0/3); its host ports (GigabitEthernet1/0, 1/1) held none, their hosts idle past
the switch's MAC aging. s1's ARP held the hosts h1 (10.10.10.100), h3 (10.10.10.102) and h2
(10.10.20.101) on its SVIs. r1's MAC table was empty (a router), its ARP and IPv6 neighbours
its routed neighbours. s1's IPv6 neighbour table was empty.

`leases.json`: four of the lab Kea's IPv4 leases as the DHCP reader stored them at
2026-10-26T08:21:20Z (read on the host, read-only), h1, h3, h2 and r6, each field as stored.
