# DHCP

The network's DHCP server, Kea: its subnets, every lease it has given, and its reservations,
under SOURCE OF TRUTH because a reservation is a statement of intent, with the leases as the
evidence beside it. The page names its network (`/v2/dhcp?list=<network>`) and draws what the
DHCP reader last read from Kea's Control Agent; it never asks Kea while you look. The reader
reads every five minutes, and the page redraws by itself when Kea's answer changes.

## What it is for {#what-it-is-for}

Seeing which address a host holds and why: a lease is a fact about a client; a reservation is
a statement of intent. Onboarding by DHCP or ZTP writes a reservation; see
[Onboard a device](onboard).

## Whose Kea {#whose-kea}

A Kea server has one owning network: the network where its connection is set in
[Settings](settings), never a network that inherits it. A network that inherits Kea shows
Default's Kea, and Default owns it. Every change to a Kea, a reservation, a subnet or an
exclusion, and onboarding's ZTP reservations (`dhcp/ztp-reservations.yml`), is recorded in its
owner's repository and published with the owner's remote, so its
history stays in one place whichever network you look from, and deleting a network that only
inherited Kea takes none of it away.

Changes are made on the owner's DHCP page. On a network that inherits Kea, the page says so
under its heading ("Branch uses Default's Kea"), links to the owner's DHCP page, and draws Kea's
subnets, leases, reservations and exclusions with no Add, Edit, Remove or Exclude. Preview and
Confirm reached there by address are refused, naming both networks ("Branch uses Default's Kea …: a change to it is made on
Default's DHCP page"), and nothing is written. Settings refuses a second network setting the
same Kea as its own, naming the network that already has it.

## The read {#read}

Under the counts, the page says which of Kea's services were read (`dhcp4` for IPv4, `dhcp6` for
IPv6), Kea's version, and how old the read is. Each family is read on its own. One that Kea did
not answer is drawn as it was last read, with its error and its age, and never blanks the other.
One that has never been read is said so, never drawn as empty.

## Subnets {#subnets}

One row per subnet, as Kea runs it: its prefix, Kea's id for it, its pools, and its lease times
(valid, preferred, renew and rebind; "–" where Kea has none, as IPv4 has no preferred lifetime).
"The same as Kea's global" says a subnet's times equal the server's; Kea reports a subnet's
times filled in from the global ones, so the page never claims more than that. Where Kea
computes renew and rebind from each lease's own lifetime (`calculate-tee-times`), the cell says
the shares, "renew at 50% · rebind at 80% of each lease", rather than two fixed times.

A client class can carry its own lease time, and it beats the subnet's: the note under the table
names each such class, whom it serves and its lifetimes. `mercury-reserved` serves every client
with a reservation, in every subnet: 7 days (IPv6 preferred 3.5 days), so a reserved host rides
out a week of Kea being down. A pool address takes Kea's global lifetime, 4 hours (IPv6
preferred 2 hours), so a client that leaves frees its address within hours. On the management
(ZTP) subnet every client takes a class's lifetime: a reserved device the reserved class's 7
days, because a lapse there cuts Mercury off the device, and an unreserved one the discovery
classes' 5 minutes. A client learns a new
lifetime at its next renewal, so a change reaches a long-held lease only when it renews. One
host step put these in place (`scripts/host-steps/e19-dhcp-lifetimes.sh`), proving nothing else
moved, as the subnet move below did.

**In use** is the active leases against the size of the pools. ZTP's subnet is marked: it has no pool and answers
only the reservations onboarding writes.

Under each pool's range is what the pool is for: the description kept with it in Kea (in the
pool's `user-context`), or, for ZTP's discovery pools, the vendor class it serves. A pool on a
subnet Mercury holds that has no description says so, and Edit… adds one: the **Pool
description** field (at most 80 printable characters; empty removes it). The description alone
is a change Kea reloads with, and changes no lease. A pool split by an exclusion keeps its
description on every piece.

Kea's subnets start out written by hand in Kea's own files. Before Mercury first changes one, a
single host step (`scripts/host-steps/c529-step5-subnet-files.sh`, run once on the host) moves
every subnet, each with its reservation file, into Mercury's own files (`subnets4.json` and
`subnets6.json` beside Kea's configuration), unchanged, and Kea's files then include them. It
takes a dated copy of Kea's configuration and lease files first, and proves nothing a client
sees changed: Kea's running configuration, every reservation and every lease are read before
and after and must be equal, with Kea's own configuration hash unchanged; otherwise it puts
Kea's files back and says what moved. The Update page's host steps say whether it has run.

## Leases {#leases}

Every lease, grouped by subnet. A group is collapsed until opened, and opens by itself when it
has something to look at: an identity holding several leases (a client that asked again and was
given a new address each time), or a lease from the pool to a host that has a reservation for
another address. **Find** matches an address, MAC, DUID or hostname; **Show** narrows to leases
sharing an identity, those not in the inventory, or those expiring within a day. Either shows a
part and says how much of the whole.

An IPv4 lease is held by its MAC, an IPv6 lease by its DUID, and an IPv6 lease also shows its
**IAID**, the identifier of the client's address association: a client that asks with a new IAID
each time is given a new address each time, which is how one DUID comes to hold several. A
client that installs its address with no lifetime ("forever", as Linux does for DHCPv6) keeps
using it whatever Kea's lease says, so a lease ending or being shortened changes nothing on the
host. A reservation for the address the host uses is the fix: the host is given that address
every time it asks. A hostname that names a device of
the network links to its page. **Kea's lease** is its lifetime and when it ends. **As the host
holds it** is the client's side, which Kea cannot see: for a host Mercury does not reach it says
"not readable", never blank; reading a managed device's own lease is designed and not built yet.

## Reservations {#reservations}

Each reservation, with what it does now: **in use by it** (a client with its identity holds the
address), **held by another client**, **unmatched** (no client has asked with its identity, and
one under its hostname asked with another, as a lab host's MAC does at each redeploy), or **no
request yet**, or **not used** (Kea's `reservations-in-subnet` or `reservations-global` is off
where it would apply, the setting named). A reservation kept at Kea's global level is listed as
its own group and counts in each subnet that turns the global ones on. Reservations Kea keeps in
a hosts database are not in its configuration: the page names the database above the tabs and
counts only the configuration's.

**Add a reservation…** reserves an address for one client in a subnet; each reservation's
**Edit…** changes the client it waits for, its address or its hostname, and **Remove…** takes it
away, saying what survives. Each opens a card in place: the change, its checks by name, what it
does not do, and a confirm with your reason, bound to the preview; the result is read back from
Kea and recorded in the network's repository ([how it works](dhcp-reservation)).
**Edit…** is the action for an **unmatched** reservation. ZTP's reservations are written by
onboarding and changed there; one written by hand in Kea's own files is shown and not changed
here.

## Exclusions {#exclusions}

Kea has no excluded-address setting, so exclusions will be Mercury's own record, each range with
its reason and where it came from, and Mercury will shape the pools around them when it writes
Kea. They arrive with the subnet operations, with the conflicts Mercury finds: an address NetBox
or intent assigns inside a pool. Nothing is excluded today.
