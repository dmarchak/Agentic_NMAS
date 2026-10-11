# Change a DHCP subnet: its pool, options and lease times

On **DHCP › Subnets**, each subnet Mercury holds has **Edit…**: its pool, its gateway (IPv4), its
DNS servers, its domain, and its lease times. Each change is an operation: the card previews it
against Kea as it runs now, a verified person confirms with a reason, and the apply tests,
writes, reloads Kea, reads it back and records it.

![Changing a subnet: the preview asks Kea, names the leases the change affects and checks the pool and the gateway; you confirm with a reason; the apply plans again and writes nothing if anything moved, tests the candidate with Kea's own check, writes it, reloads Kea, and reads Kea's configuration back, putting the previous file back unless exactly this subnet changed; then one commit with your reason.](diagrams/dhcp-subnet.svg)

## Where a subnet lives

Every subnet is in Mercury's own file beside Kea's configuration, `nmas/subnets4.json`
(`nmas/subnets6.json` for IPv6), which Kea's configuration includes; each subnet's reservations
stay in their own file, which the subnet includes. One host step, once, moved Kea's hand-written
subnets there (see [DHCP](dhcp)). Until it has run, Edit… is not offered and a change is
refused, naming the step. ZTP's subnet is onboarding's, and is changed only where onboarding
sets it.

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
  address on its interfaces), said when it differs; Kea's own check on the candidate runs when you
  confirm; Mercury's subnet file is the version the preview read.

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
5. `read-back`: Kea's configuration is read again: exactly this subnet changed, and every other
   subnet and setting as before. Anything else puts the previous file back, reloads, and says
   what moved.
6. `record`: `dhcp/subnets.yml` in the network's repository (every subnet as Mercury's files
   hold them) is committed as you, with your reason in its body. It shows on History.

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
- It does not add, remove or exclude: those are the next subnet operations and board D's
  exclusions.
