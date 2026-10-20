# Change a DHCP subnet: its pool, options and lease times

On **DHCP › Subnets**, each subnet Mercury holds has **Edit…** (its pool, its gateway for IPv4,
its DNS servers, its domain, and its lease times) and **Remove…**, and **Add a subnet…** sits
beside the heading. Each is an operation: the card previews it against Kea as it runs now, a
verified person confirms with a reason, and the apply tests, writes, reloads Kea, reads it back
and records it.

![Changing a subnet: the preview asks Kea, names the leases the change affects and checks the pool and the gateway; you confirm with a reason; the apply plans again and writes nothing if anything moved, tests the candidate with Kea's own check, writes it, reloads Kea, and reads Kea's configuration back, putting the previous file back unless exactly this subnet changed; then one commit with your reason.](diagrams/dhcp-subnet.svg)

## Adding a subnet {#add}

Give the family, the prefix and its pool; the rest is offered. From committed intent: the
interfaces on the prefix are Kea's relay addresses for it (Kea matches a relayed request to the
subnet by them), the VRRP group's virtual address is its gateway (IPv4), and the interface's name
gives the Kea id (VLAN 30 is id 30 when free, else one more than the highest id in use). The checks say whether an
interface in intent relays the prefix to a DHCP server, and refuse a prefix that overlaps one
Kea already serves. A prefix no interface in intent is on is said plainly: no relay brings a
client's request, so Kea would answer nobody on it. The new subnet takes its reservations from a
fresh file of Mercury's, created empty.

### For ZTP onboarding {#add-for-ztp}

The card's Subnet part has a checkbox, **For ZTP onboarding** ("a device behind a relay, IPv4
only: its reservations are written by Add device, and it carries no gateway or DNS option"),
unticked by default. Tick it to add a subnet a device is onboarded on by ZTP behind a relay
([ZTP behind a relay](onboard#ztp-behind-a-relay)); a pool is still needed. The subnet then
carries Mercury's mark (`"user-context": {"mercury-ztp": "relayed"}`, in the preview's change and
in `dhcp/subnets.yml`), the tick is part of the preview's hash, and its reservations file is
onboarding's alone: Add device writes it, and a reservation there on this page is refused. Its
relay address is the one interface the network's committed intent has on the prefix, and that
interface must relay to a DHCP server over IPv4 (`ip helper-address`). Refused, each by name: a
prefix no device Mercury manages has an interface on ("no device Mercury manages has an interface
on … in committed intent"); a prefix with more than one interface in intent, a VRRP pair among
them ("expected exactly one relay interface on …", naming each); and an interface that relays to
no DHCP server. The preview's checks lead with "for ZTP behind <device> <interface> (<address>,
its relay); its reservations are onboarding's, and it carries no gateway or DNS option (D4)".
The subnet carries no gateway and no DNS option: Gateway (3) and DNS servers (6) stay on the
card, and a value in either is refused at the preview ("a relayed ZTP subnet carries no gateway
or DNS option (D4)"); option 3, the relay's own address, is a reservation's own choice, made at
Add device. ZTP is IPv4 only: an IPv6 subnet for ZTP is refused by name. The subnet also says
`"match-client-id": false` (a check: "match-client-id false: a lease is matched by the device's
MAC"): Kea then matches a lease to its device by the MAC the reservation names, never by the
client-id the device sends, so a device redeployed with a new client-id is answered with its
reserved address instead of meeting its own old lease as another client's (C1403, measured on
this installation's Kea). Without the tick the Add is as above.

## Removing a subnet {#remove}

The card says what the removal does to the clients served now: each client holding a lease keeps
its address until its lease ends, and from its next renewal Kea answers it nothing on this
subnet; its reservations go with it. When any client or reservation is affected, the confirm
needs the acknowledgement ticked, and is refused without it. **What survives:** the subnet's
definition and its reservations stay in the repository's history (`dhcp/subnets.yml`,
`dhcp/reservations.yml`), so adding it back is one Add; Mercury's reservations file for it stays
on disk, included by nothing. ZTP's subnet, the one this host is on, is onboarding's and never
removed here. A subnet added for ZTP behind a relay is Mercury's: its row is marked ZTP, Held by
Mercury, with **Edit…** and **Remove…**. Its removal is refused while onboarding holds any
reservation in it, naming how many ("subnet 40 is a relayed ZTP subnet holding 2
reservation(s) onboarding wrote: abandon or retire those devices first"), because each device's
abandon or retirement removes its own; once it holds none, the removal is planned like any
other.

## Editing a subnet added for ZTP behind a relay {#edit-relayed-ztp}

Its **Edit…** changes its pool, the pool's description, its domain and its lease times, as for
any subnet, and keeps its ZTP mark and its relay address; one added before C1403 gains
`"match-client-id": false` with its next edit, said in the change. D4 holds: such a subnet never carries
a route or resolver option. Gateway (3) and DNS servers (6) stay on the card, and a value in
either is refused at the preview, naming the value and what D4 allows. Option 3 may be only the
relay's own address, and only on a reservation that chose it at Add device, never at the subnet,
where it would reach every device there ("D4: option 3 (routers) 198.51.100.2 at the subnet: on
relayed ZTP subnet 40 option 3 may be only the relay's own address (198.51.100.1), and only on a
reservation that chose it at Add device"). Option 6 is never sent. The subnet the edit would
leave is checked too: a route or resolver option already on it or on a pool (`routers`,
`domain-name-servers`, `static-routes`, `classless-static-route`), whoever put it there, refuses
the edit, naming each. Its checks say D4 in place of the gateway's comparison with intent: a ZTP
subnet carries no gateway, so intent's VRRP address is not its value. Its reservations stay
onboarding's. The mark is IPv4's alone: ZTP is IPv4 only (C1245), so an IPv6 subnet carrying
it is an ordinary subnet.

## Where a subnet lives

Every subnet is in Mercury's own file beside Kea's configuration, `nmas/subnets4.json`
(`nmas/subnets6.json` for IPv6), which Kea's configuration includes; each subnet's reservations
stay in their own file, which the subnet includes. One host step, once, moved Kea's hand-written
subnets there (see [DHCP](dhcp)). Until it has run, Edit… is not offered and a change is
refused, naming the step. ZTP's subnet, the one this host is on, is onboarding's, and is
changed only where onboarding sets it; a subnet added for ZTP behind a relay is edited here,
held to D4 ([above](#edit-relayed-ztp)). A network whose Kea is its own keeps its ZTP reservations in that Kea's ZTP file, and
the ZTP responder serves every network's, each from its Kea owner's file.

## The preview

The card reads Mercury's subnet file and asks Kea for its configuration and its leases. Sent:
nothing. Recorded: nothing. It says:

- **The change:** each of the subnet's settings that would move, as Kea's file says it, before
  and after.
- **Leases now:** every client holding an address the new pool leaves out, by address, MAC or
  DUID and host. Such a client **keeps its address until its lease ends**: measured on Kea 2.4.1,
  Kea answers its renewals with silence, and when the lease ends the client asks again and is
  given an address from the new pool. A reserved address is never stranded by a pool change. A
  new lifetime applies to leases granted or renewed after the change.
- **Checks**, each by name: the pool lies inside the subnet and overlaps no other subnet's pool;
  the gateway against intent's first-hop address for the prefix (the VRRP group's virtual
  address on its interfaces), said when it differs, or, on a subnet added for ZTP behind a
  relay, that it carries no route or resolver option (D4); Kea's own check on the candidate runs
  when you confirm; Mercury's subnet file is the version the preview read.

**IPv6** has no gateway option: a host's default route comes from the routers' advertisements on
the link. The card reads from intent whether each router advertising on the prefix sets M
(`ipv6 nd managed-config-flag`, needed for a host to take an address here) and O
(`ipv6 nd other-config-flag`, for the options alone), and links to the device's intent where one
does not. This page never changes a device.

## The apply

The confirm needs a verified person and a reason. It is bound to the preview's hash: the subnet
as it was, as it becomes, and the version of Mercury's subnet file. The apply holds the file
from its first read to its read-back, so a second person's change waits rather than
interleaving:

1. `plan`: Kea and Mercury's subnet file are read again and the hash compared. Moved since the
   preview: nothing is written, and the card says preview again.
2. `test`: the candidate file is tested with Kea's own check (`kea-dhcp4 -t`, or `kea-dhcp6 -t`)
   on a copy of the running configuration that includes it. Refused: Mercury's file is not
   touched.
3. `write`: Mercury's subnet file is replaced by the tested candidate.
4. `reload`: Kea reloads its configuration through its API (`config-reload`). A failed reload
   puts the previous file back and reloads that.
5. `read-back`: Kea's configuration is read again: exactly this subnet changed (or, for an add,
   is there; for a removal, is gone), and every other subnet and setting as before. Anything
   else puts the previous file back, reloads, and says what moved.
6. `record`: `dhcp/subnets.yml` in the repository of the network that owns this Kea
   ([Whose Kea](dhcp#whose-kea); every subnet as Mercury's files hold them) is committed as
   you, with your reason in its body. It shows on History.

## When it goes wrong

- **Kea cannot be asked**, or its leases cannot be read: refused, naming the error.
- **Kea's own check refuses the file:** nothing is written; its words are shown.
- **The read-back disagrees:** the previous file is put back and Kea reloaded; the card says what
  moved.
- **The record fails after Kea has the change:** said in red; Kea holds the change, and the next
  change records it.

## What a subnet change does not do

- It does not end a lease or move a client now: a client outside the new pool keeps its address
  until its lease ends.
- It does not change a device: a gateway or an RA flag that intent does not have is changed in
  that device's intent and deployed.
- It does not exclude addresses from a pool: that is DHCP › Exclusions.
