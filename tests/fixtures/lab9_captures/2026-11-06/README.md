# Lab 9 device captures, 2026-11-06 (real, masked): the lab as brought up

Real captures from the lab's hardware and controller after the bring-up of 2026-11-06, kept
as captured. The masking is the same as the 2026-11-05 set's (`../README.md`): passwords,
hashes, SNMP communities, keys and certificates, serial numbers, login users, machine and boot
ids, host-key fingerprints and link-local addresses are masked, terminal escape codes are
stripped, MACs are replaced consistently, and the lab's own device names are neutralised.
Nothing else is changed, so a parser or golden test reads what a device printed.

What this set adds to the masking:
- **Addresses by a fixed map:** the management network becomes 192.0.2.0/24 (as in the
  2026-11-05 set), the data network 198.51.100.0/24 and the router's uplink 203.0.113.0/24;
  the upstream device's address and name (outside the lab) are `<redacted>` and
  `<upstream-device>`. Public resolvers and NTP servers are kept.
- **Datapath ids that embed a switch MAC** (both Aristas and the ProCurve) are replaced
  consistently with that MAC's replacement, in decimal, 16-hex and `0x` forms, so a DPID still
  matches its switch across files; Open vSwitch's fixed ids (3 and 4) are kept.
- Ryu's `serial_num` and the router's licence UDI serial are masked.
- `ovs-vsctl show`'s first line, the Open_vSwitch database's UUID (random per installation,
  like the machine id), is `<redacted>` on both OVS hosts and the controller.

Two sets: the 2026-11-05 files beside this folder show the lab BEFORE the operator's changes;
these show it AFTER (OpenFlow configured and connected on all five switches).

| File | Device | Software |
|---|---|---|
| `arista-sw1.txt`, `arista-sw2.txt` | Arista DCS-7050Q-16 | EOS 4.17.0F |
| `procurve-sw.txt` | HP 3500yl-24G (J8692A) | K.16.02.0020 |
| `mgmt-sw.txt` | Cisco WS-C2960-24TT-L, the management switch | IOS 12.2(58)SE2 |
| `router.txt` | Cisco 3825, the lab gateway (NAT, DHCP, NTP) | IOS 15.1(4)M8 |
| `ovs1.txt`, `ovs2.txt` | Dell PowerEdge R430 OVS hosts | Ubuntu 24.04.3, Open vSwitch 3.3.4 |
| `controller.txt` | the SDN controller (its network and host reads; Ryu is not in it) | Ubuntu 16.04.5 |
| `ryu-rest.txt` | Ryu's REST answers: `/stats/switches`, `/v1.0/topology/links`, and `desc` and `portdesc` per switch | Ryu 4.34 (the operator's record; the answers carry no version) |

Each device file runs from the first prompt to the session's `exit`; repeated blank lines are
collapsed to one, as in the 2026-11-05 set.
