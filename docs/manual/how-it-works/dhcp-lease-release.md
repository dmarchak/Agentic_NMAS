# Release a DHCP lease

Kea holds a lease until it ends, and a reserved address takes a 7-day lease. A lease that nobody
will renew still holds its address for the rest of that time: a device retired, an onboarding
abandoned, or a virtual machine recreated with a new client identifier. While it does, Kea
refuses the address to the client the reservation now names. On **DHCP › Leases**, each lease's
**Release lease…** deletes one lease from Kea. It is an operation: previewed against Kea,
confirmed by a verified person with a reason, released, read back and recorded.

![Releasing a lease: the preview names the lease, its client and whether the address is reserved; you confirm with a reason; the apply reads Kea's leases again and compares the hash, sends lease4-del or lease6-del for that address alone, and reads the leases back; then one commit with your reason.](diagrams/dhcp-lease-release.svg)

## The preview

The preview asks Kea for its leases in the lease's family (IPv4 or IPv6) and names the one on
the address: its client (MAC, client-id or DUID), its hostname, its state and when it was last
renewed. It also asks Kea's configuration whether the address is reserved, and for whom. A
reservation stays: Kea gives the address to the reserved client at its next request. An address
with no reservation returns to its subnet's pool, if it lies in one.

The preview refuses, saying why, when Kea holds no lease on the address now, when it holds more
than one (which one is meant cannot be told from the address), and when this network uses
another network's Kea ([Whose Kea](dhcp#whose-kea)): the release is made on the owner's page.
An active lease is released all the same, and the preview says what that means: Kea cannot tell
whether the client still uses the address, and a client that does keeps using it until it next
renews, and is then answered afresh.

## The steps

1. `plan`: Kea's leases are read again and the hash compared with the preview's. A lease that
   moved (another client on the address, or none) refuses, and nothing is released.
2. `release`: `lease4-del` or `lease6-del` for that address alone, through Kea's control agent
   (its `lease_cmds` hook).
3. `read-back`: Kea's leases are read again. The release is claimed only when Kea holds no lease
   on the address for that client.
4. `record`: the release is committed in `dhcp/released-leases.yml` in the repository of the
   network that owns this Kea, with the lease's client, who released it, when, and your reason.

A deleted lease cannot be put back: Kea keeps no copy of it, so the commit is the record. Nothing
on the client changes, since a lease deleted in Kea is not a message to the client.

## Retire and Abandon

[Retire](retire) and a ZTP device's Abandon release the leases the device leaves behind, through
the same release: every lease Kea holds for the device's MAC or for an address it was known by,
in either family, named in their plan and released, read back and recorded at the apply. A lease
on one of those addresses that Kea now holds for another client is left, and said.
