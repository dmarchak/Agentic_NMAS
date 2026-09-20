# Config fixtures

Sanitized real golden configs from the reference lab. Credential hashes have
been replaced with structurally valid fakes; everything else is as the devices
report it.

| File | Platform | Features exercised |
|---|---|---|
| `s1_vios_l2.cfg` | vIOS-L2, IOS 15.2 | RIPv2 + RIPng, VLANs, trunk/access switchport, SVIs, VRRPv3 dual-stack, DHCP relay v4+v6, tracking, SNMP, banners, no NETCONF |
| `r1_c8000v.cfg` | C8000v, IOS-XE 17.6 | OSPFv2 + OSPFv3, RIPv2 + RIPng, VRF, crypto PKI chains, IP SLA, ACL, telemetry subscriptions, NETCONF/RESTCONF |

The two platforms differ in exactly the ways that justify separate parser
modules: telemetry/NETCONF blocks, VLAN and switchport handling, and
running-config defaults.
