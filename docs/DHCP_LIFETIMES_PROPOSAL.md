# DHCP lifetimes for reserved and pool addresses (a proposal; E19)

**The operator's Phase 7 list, E19 (2026-10-13): propose DHCP valid and preferred lifetimes. A
proposal only: nothing is changed on Kea until the operator chooses.** It covers what the lab's
leases are today, measured, what is wrong with that, the proposed lifetimes for each kind of
address, where Kea holds them and how Mercury would write them, the migration, and the
decisions.

## 1. Today, measured

Read 2026-10-13 from the DHCP reader's stored value (Kea's own configuration, no device read):

| What | Valid | Preferred (IPv6) | Renew (T1) | Rebind (T2) |
|---|---|---|---|---|
| Every IPv4 subnet | 31,536,000 s (365 days) | n/a | 15,768,000 s (182.5 days) | 27,594,000 s (319 days) |
| Every IPv6 subnet | 365 days | 365 days | 182.5 days | 319 days |
| The ZTP discovery classes (`dhcp_discovery`) | 300 s | n/a | Kea's own | Kea's own |

One lifetime for every address, reserved or from a pool, and it is a year. Mercury already
writes a subnet's valid lifetime (and IPv6's preferred) from DHCP › Subnets › Edit…, setting
renew at half and rebind at seven eighths (`modules/dhcp_subnets.py`).

## 2. What a year costs

- **A pool address is held for a year by whatever took it once.** A lab host started once,
  or a probe, keeps its pool address until the lease expires; orphan leases (C681's four on
  h1, and the one still standing, 2001:db8:20::100) live as long.
- **A change reaches a client only at its renew: up to six months.** A reservation moved,
  a DNS server changed, a pool renumbered: a client that does not restart keeps the old
  answer for up to 182 days.
- **A retired device's address is not free for a year**, even though its reservation is
  gone.
- **IPv6 has no deprecation step:** preferred equal to valid means an address goes from
  preferred straight to invalid; a renumbering cannot move clients gracefully.

## 3. The proposal

| Kind of address | Valid | Preferred (IPv6) | Renew / rebind | Why |
|---|---|---|---|---|
| **Reserved** (a host reservation: every managed device and lab host) | 1 day | 12 hours | Kea's default share: 50% / 87.5% | The address is fixed by the reservation whatever the lease length, so the lease only bounds how long a change takes to arrive (12 h) and how long a removed reservation's address stays taken (1 day). Renewal costs two exchanges a day per client. |
| **Pool** (dynamic) | 4 hours | 2 hours | 50% / 87.5% | Transient clients return their address within hours; a pool sized for its population never fills with the gone. |
| **Management segment** (a device whose path to Mercury is a DHCP address, C673's shape) | 7 days, renew 1 day | 3.5 days | 1 day / 6 days | A lease that lapses there cuts Mercury off the device. A week rides out a Kea outage a person will see on Needs attention (the DHCP reader's own row when Kea does not answer) long before it matters. |
| **ZTP discovery** (`dhcp_discovery`) | unchanged, 300 s | n/a | unchanged | A first-boot device must come back quickly to the address its reservation gives. |

The numbers follow the common enterprise practice (8 to 24 hours for dynamic clients, a day or
more for fixed ones), shortened for the pool because this lab's dynamic clients are transient.
**None of them is measured yet**: the walk after the change measures renewals per hour against
Kea's own counters, and the pool's peak occupancy.

## 4. Where Kea holds them, and how Mercury writes them

- **Pool lifetimes** are the subnet's own (`valid-lifetime`, `preferred-lifetime`), which
  DHCP › Subnets › Edit… already writes, previewed and confirmed.
- **Reserved lifetimes** come from a client class: one class, `mercury-reserved`, defined with
  its own `valid-lifetime` and `preferred-lifetime`, and named in every reservation Mercury
  writes (`client-classes`). Kea takes a class's lifetime over its subnet's. The
  management segment is a second class, `mercury-management`, on that segment's reservations.
- **To measure before building:** the running Kea's version supports lifetimes on a client
  class (the reader's stored value does not record the version; Mercury's Kea integration can
  ask, read-only).
- **In Mercury:** the reservations writer (`dhcp_reservations`) adds the class to every
  reservation it writes; the class definitions are Mercury's file, beside the subnets
  (C529's files), written through the same preview and confirm. DHCP › Subnets shows both
  lifetimes per subnet, reserved and pool; a new card or column needs its board first.

## 5. Migration

A client learns a new lifetime at its next renew, which today is up to six months away. So:

1. Lower the subnet lifetimes and add the classes (one confirmed change per segment).
2. Lab hosts: a restart, or `dhclient -r && dhclient` (and the IPv6 equivalent), picks the new
   lease up at once. Each is the operator's, on the hosts the operator names.
3. Managed devices: their DHCP-learned management address renews on its own schedule. Before
   the management segment changes, the change to the path the tool reaches a device on needs
   its repair route (CLAUDE.md: a change to the path to the device), which is the console.
4. The walk: renewals per hour and pool occupancy read from Kea's counters for a day, and the
   orphan lease that remains (2001:db8:20::100) expiring on its own within a day.

## 6. The operator's decisions

1. The four rows' numbers (or other ones).
2. Reserved lifetimes by client class (this proposal), or per reservation.
3. Whether the management segment keeps a long lease, or moves its devices to static
   management addresses (C673).
4. Whether DHCP › Subnets draws both lifetimes (a board revision first).
