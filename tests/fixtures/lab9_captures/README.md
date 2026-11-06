# Lab 9 device captures (real, masked)

Real captures from the lab's hardware, 2026-11-05, kept as captured: the only edits are the
masking before they entered the repository (passwords, hashes, SNMP communities, keys and
certificates, serial numbers, login users, machine and boot ids, host-key fingerprints, link-local
addresses), with addresses moved to 192.0.2.x, MACs replaced consistently and the lab's own
device names neutralised. Nothing else is changed, so a parser test reads what a device printed.

| File | Device | Software |
|---|---|---|
| `mgmt-sw.txt` | Cisco WS-C2960-24TT-L, the management switch | IOS 12.2(58)SE2 |
| `arista-sw1.txt`, `arista-sw2.txt` | Arista DCS-7050Q-16 | EOS 4.17.0F |
| `procurve-sw.txt` | HP 3500yl-24G (J8692A) | K.16.02.0020 |
| `ovs1.txt`, `ovs2.txt` | Dell PowerEdge R430 OVS hosts | Ubuntu 24.04.3, Open vSwitch 3.3.4 |
| `controller.txt` | the SDN controller | Ubuntu 16.04.5 |

**They show the state BEFORE the operator's changes of 2026-11-05**, not the lab as it is now:
- the management switch still has VLANs 10 and 50 (removed after the capture);
- ovs1 still has its old `br0` bridge (deleted after the capture); ovs2's `eno1` still holds a
  stale untagged address (removed after the capture);
- the controller still has its old hostname (renamed after the capture) and no Ryu.

**The management switch's capture** is the first of about 4,000 identical passes the capture
session repeated (a 1.1 GB file); only that first pass is kept.
