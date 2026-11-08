# NSOT export fixtures

`lab9_records.json` holds NetBox 4 REST records (devices with their rendered `config_context`,
interfaces, IP addresses, VLANs, prefixes, the `openflow` Service and cables) for the Lab 9
fabric as the 2026-11-06 masked captures show it (`../lab9_captures/2026-11-06/`), in the
captures' masked addresses (192.0.2.0/24 management, 198.51.100.0/24 data) and neutral names.

**It is derived from the captures, not read from NetBox.** Each value is the one the matching
capture shows: the management addresses and interfaces (`Management1`, the ProCurve's VLAN 100
interface, the OVS hosts' `eno1.100` on its parent `eno1`, `eno1.100@eno1` in the captures'
`ip link`), the OpenFlow ports (the Aristas' `bind interface` lines,
the ProCurve's VLAN 200 members, the OVS bridges' ports), each port's `openflow_port` (Ryu's
`portdesc` in `ryu-rest.txt`: the Aristas' interface numbers, the ProCurve's port numbers, the
OVS ports' 1 to 3), the instance names (`lab9`, `br0`), the OVS datapath ids (3 and 4) and the
controller's address and port. The NetBox-only fields (ids, slugs, `last_updated`) are typed
in NetBox's shapes. The masked export of the verified NetBox snapshot replaces it once that
read is made (the register's row for it).
