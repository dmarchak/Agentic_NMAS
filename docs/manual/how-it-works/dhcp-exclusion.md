# Exclude addresses from a DHCP pool

Kea has no excluded-address setting, so Mercury models exclusions. On **DHCP › Exclusions**,
**Add an exclusion…** keeps a range (or one address) of a subnet out of its pool, named with its
reason; each exclusion's **Remove…** gives the addresses back. A conflict, a static address
inside a pool, has **Exclude…**, which opens the same card with its reason filled from where the
address is assigned. Each change is an operation: previewed against Kea, confirmed by a verified
person with a reason, written through the subnet's write, read back and recorded.

![Excluding addresses: the preview computes the pieces of the pool Kea is given and the leases on the excluded addresses; you confirm with a reason; the apply is the subnet's write, plan again, Kea's own check on a candidate, write, reload, read back exactly this subnet's pools or put the previous file back; then one commit with your reason.](diagrams/dhcp-exclusion.svg)

## The range and the pieces

You set a subnet's pool as **one range** (on DHCP › Subnets). Kea is given the pieces of that
range the exclusions leave: excluding `10.10.10.120 - 10.10.10.129` from the pool
`10.10.10.100 - 10.10.10.199` gives Kea `10.10.10.100 - 10.10.10.119` and
`10.10.10.130 - 10.10.10.199`. The range as set and the exclusions are Mercury's record in the
repository of the network that owns this Kea ([Whose Kea](dhcp#whose-kea);
`dhcp/exclusions.yml`, beside `dhcp/subnets.yml`), read as committed, so a
person edits the range and the reason and never the arithmetic. An exclusion outside the pool
today is kept: it stays out if the pool grows. A reservation for an excluded address is allowed,
and said: a fixed address kept out of the pool is the usual way to give one out.

## Conflicts

The DHCP reader reads committed intent on each run, and every static address an interface is
given is compared with each pool. One inside a pool and not excluded is a conflict: the
Exclusions tab lists it with the interface that holds it and whether Kea has given the address
out (if it has, two hosts may answer on it until the lease ends). NetBox's assigned addresses
are not compared yet.

## The preview

It reads the committed record and Mercury's subnet file, and asks Kea for its configuration and
leases. Sent: nothing. Recorded: nothing. It says:

- **The pools as Kea is told:** the pieces before and after.
- **Leases now:** a client holding an excluded address keeps it until its lease ends (measured on
  Kea 2.4.1: its renewals are answered with silence), and is then given an address from the
  pool.
- **Checks:** the range lies inside the subnet and overlaps no recorded exclusion; whether it is
  inside the pool today; a reservation on an excluded address, said; Kea's own check at confirm.

A removal says what survives: the exclusion stays in the repository's history, and its addresses
return to the pool.

## The apply

The confirm needs a verified person and a reason, and is bound to the preview's hash. It is the
subnet's write, holding Mercury's subnet file from its first read to its read-back:

1. `plan`: Kea, Mercury's subnet file and the committed record are read again and the hash
   compared. Moved since the preview: nothing is written.
2. `test`: the subnet file with the pool's pieces is tested with Kea's own check on a copy of the
   running configuration.
3. `write`: Mercury's subnet file is replaced by the tested candidate.
4. `reload`: Kea reloads its configuration through its API; a failed reload puts the previous
   file back.
5. `read-back`: Kea's configuration is read again: exactly this subnet's pools changed. Anything
   else puts the previous file back and reloads.
6. `record`: `dhcp/exclusions.yml` and `dhcp/subnets.yml` are committed as you, with your reason
   in its body. It shows on History.
