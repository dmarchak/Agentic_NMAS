# Reserve an address: add, change or remove a DHCP reservation

On **DHCP › Reservations**, **Add a reservation…** reserves an address in a subnet for one
client, and each reservation's **Edit…** and **Remove…** change it or take it away. A reservation
tells Kea to give that client that address, every time it asks. Each change is an operation: the
card previews it against Kea as it runs now, a verified person confirms with a reason, and the
apply writes, reloads Kea, reads it back and records it.

![Reserving an address: the preview asks Kea and checks the address, the client and the leases; you confirm with a reason; the apply plans again and writes nothing if anything moved, tests the candidate with Kea's own check, writes it, reloads Kea, and reads every reservation back, putting the previous file back if anything differs; then one commit with your reason.](diagrams/dhcp-reservation.svg)

## Where a reservation lives

Each subnet's reservations are in a file of Mercury's beside Kea's configuration,
`nmas/reservations-<id>.json` (`nmas/reservations6-<id>.json` for IPv6), which Kea's configuration
pulls in for that subnet. Never only in Kea's memory: a reservation sent to a running Kea and not
written to a file it reads is gone at its next restart. Kea's own configuration files are the
host's; one host step, once, gives each subnet its file (empty at first), with Kea's running
configuration compared before and after so nothing a client sees changes. A subnet whose
configuration does not take its reservations from Mercury's file is refused, naming the file and
that step.

The ZTP subnet's reservations are onboarding's (**Devices › Add device**), and are changed there.
A reservation written by hand in Kea's own files is shown, and is not changed here.

## The preview

The card asks Kea for its configuration and its leases and reads Mercury's file for the subnet.
Sent: nothing. Recorded: nothing. It says:

- **Change:** the lines that would be added to or removed from the subnet's reservations.
- **Checks**, each by name:
  - the address is inside the subnet, and whether it is inside its pool (so no other client may
    be given it while it is reserved) or outside (only this client is ever given it). An address
    outside the subnet is refused: it would be *stranded*, a reservation Kea can never give;
  - no other reservation in the subnet names this client or this address;
  - no other client holds a lease on the address now. One that does is refused, naming the
    client, its lease's end and when Kea was read;
  - Kea's own check on the candidate file runs when you confirm;
  - Mercury's file for the subnet is the version the preview read;
  - no reservation Kea holds is stranded, in any subnet, shared network or at its global level.
    A hosts database, whose reservations Kea's configuration does not list, refuses every change:
    a conflict there could not be seen.
- **Not done:** what the reservation does not change. A client keeps an address it holds until
  it asks again, and takes the reserved one then; a client holding other addresses keeps them
  until they end (named, never removed). A removal says what survives: the client keeps its
  address until its lease ends, and the reservation stays in the repository's history.

Kea reserves by the identities it matches on (its `host-reservation-identifiers`): for IPv4 a
MAC, a DUID or a client-id; for IPv6 a DUID or a MAC.

## The apply

The confirm needs a verified person and a reason. It is bound to the preview's hash: what the
reservation was, what it becomes, and the version of Mercury's file. The apply holds the
subnet's file from its first read to its read-back, so a second person's change waits rather
than interleaving:

1. `plan`: Kea and Mercury's file are read again and the hash compared. Moved since the
   preview: nothing is written, and the card says preview again.
2. `test`: the candidate file is tested with Kea's own check (`kea-dhcp4 -t`, or `kea-dhcp6 -t`)
   on a copy of the running configuration that includes it. Refused: Mercury's file is not
   touched.
3. `write`: Mercury's file for the subnet is replaced by the tested candidate.
4. `reload`: Kea reloads its configuration through its API (`config-reload`). A failed reload
   puts the previous file back and reloads that.
5. `read-back`: every reservation Kea holds is read again, in every subnet, shared network and at
   its global level: exactly the change shown, and nothing else moved, nothing newly stranded.
   Anything else puts the previous file back, reloads, and says what Kea held.
6. `record`: `dhcp/reservations.yml` in the network's repository (every reservation in
   Mercury's files) is committed as you, with your reason in its body. It shows on History.

## When it goes wrong

- **Kea cannot be asked**, or its leases cannot be read: refused, naming the error. An unreadable
  lease list is "cannot check", never "free".
- **Kea's own check refuses the file:** nothing is written; its words are shown.
- **The read-back disagrees:** the previous file is put back and Kea reloaded; the card says
  what was expected and what Kea held.
- **The record fails after Kea has the change:** said in red; Kea holds the reservation, and the
  next change records it.

## What a reservation does not do

- It does not end a lease or move a client now: the client takes the reserved address at its
  next request. To move it now, release and renew on the client.
- It does not change a subnet, a pool or an option: those are the subnet operations.
