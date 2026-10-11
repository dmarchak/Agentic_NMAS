# Fidelity: DHCP (C529 step 1)

The DHCP page as built, compared region by region with its approved board (C650's step). Read
from shots of the board and the page side by side, in the same headless Firefox, the page fed by
the DHCP reader's value built from the lab's Kea 2.4.1 answers (`tests/fixtures/kea/`,
`tests/test_board_shots.py::test_dhcp`).

Boards: `DhcpNetwork.dc.html` (board A, 1440 wide) on the mockups canvas, page "Item 5, DHCP on v2", approved 2026-10-06 with boards B to D and the sidebar move (canvas v59; register C529). Re-read from the canvas 2026-10-11 before building. Board A draws its three tabs one under another; the page shows one at a time. It has no phone variant: at 390 the page keeps each table whole and scrolls it in its box. Boards B (a reservation's operations), C (subnets and options) and D (exclusions) are later steps.
Shots: desktop 1440 and 1280 (Subnets), 1440 (Leases, Reservations, Exclusions); phone 390 (each tab, and its first screen). Compared 2026-10-11.
Templates compared: templates/v2/dhcp.html, templates/v2/_dhcp_view.html
Templates sha256: `fc3d6a1dc7df7a03fe5f4d897253df4cbeb8753d19241d492a8e115e94f65201`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | DHCP under SOURCE OF TRUTH, after NetBox | the same, current on this page | **same** |
| Header | "DHCP", the network chip, How does this work? | "DHCP" and the chip; the page's help is the (i) beside the title, as on every v2 page (C505: a "How does this work?" sits beside the control it explains, and the header has none) | **same** |
| Counts | subnets (IPv4 incl. ZTP, IPv6), active leases, reservations, unmatched, leases sharing a DUID | the same counts and flags | **same** |
| Whose reservations | "(5 the tool's, 2 ZTP's)" | not drawn: who wrote a reservation is known once Mercury owns the files | **later** C529 step 2 (the host step that moves the subnets into Mercury's files) |
| The read | Kea's services and version, the read's age, every 5 minutes and after every reservation change; each family on its own | the same, without "after every reservation change" (no operation changes one yet); a family not answered drawn as last read with its error, one never read said so | **later** "after every reservation change": step 2 |
| Tabs | Subnets, Leases, Reservations, Exclusions with its count and conflicts | the same four; Exclusions without a count (nothing is excluded) | **same** |
| Subnets | subnet, Kea id, pools, lease times, in use of the pool, reservations; ZTP's marked with its discovery range | the same columns; the lab's ZTP subnet has no pool, said so | **same** |
| Lease times' source | "from Kea's global level" | "the same as Kea's global" | **deviation** (log: DHCP's lease times are said to equal the global ones) |
| Reservations column | "2, in the tool's file for subnet 10" | the count; whose file is known after the move | **later** C529 step 2 |
| The subnets' note | "Every subnet is Mercury's" after the one host step | Kea's subnets are written by hand today, and the host step that moves them comes before Mercury's first change | **later** board C's host step (C529 step 2) |
| Leases | find by address, MAC, DUID or hostname; Every lease, Sharing an identity, Not in the inventory, Expiring within a day; groups by subnet, collapsed until opened | the same; a group opens by itself when flagged, searched or filtered, and a subset says how much of the whole | **same** |
| One client's several leases | together, "the same DUID" after the first, the DUID-LL read for its MAC, the drift said once beside them | the same | **same** |
| A managed device's lease | its device linked; "As the host holds it" read from the device, marked pending | the same, pending ("designed, not built") as the board marks it | **same** |
| "As the host holds it" | "not readable" for a host the tool does not reach, never blank; the note | the same | **same** |
| ZTP's leases | "3 asking, unknown: board L's list, Onboard › Discovered" (a link) | the count, and the Discovered list named in words, not built yet | **later** board L |
| Reservations | subnet, host, reserved by, address, Now (in use by it, unmatched with why, pending, no request yet) | the same columns and states, and "held by another client" | **same** |
| Add, Edit, Remove | a button and a row's actions (board B) | not drawn; the note says they arrive next | **later** C529 step 2 |
| ZTP's reservations | "Open r8's plan" | not drawn: the lab's Kea holds none, and the plan page is onboarding's | **later** board M |
| Unmatched as Needs attention | a row naming the reservation, its action Edit… | not drawn: its action is board B's | **later** C529 step 2 |
| ZTP's subnet and board L | one store, two views: the Discovered list and this page | the ZTP group's line names the Discovered list | **later** board L |
| For the operator | how a reservation reaches Kea, the two ways | not drawn: the board's note to the operator, whose decision (option 1) is recorded in C529 | **same** |
| Exclusions | board D: named exclusions and the conflicts found | what Kea cannot do and when Mercury's arrive | **later** C529 step 3 |
