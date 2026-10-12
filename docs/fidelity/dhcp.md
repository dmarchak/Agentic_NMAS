# Fidelity: DHCP (C529 step 1)

The DHCP page as built, compared region by region with its approved board (C650's step). Read
from shots of the board and the page side by side, in the same headless Firefox, the page fed by
the DHCP reader's value built from the lab's Kea 2.4.1 answers (`tests/fixtures/kea/`,
`tests/test_board_shots.py::test_dhcp`).

Boards: `DhcpNetwork.dc.html` (board A, 1440 wide) on the mockups canvas, page "Item 5, DHCP on v2", approved 2026-10-06 with boards B to D and the sidebar move (canvas v59; register C529). Re-read from the canvas 2026-10-11 before building. Board A draws its three tabs one under another; the page shows one at a time. It has no phone variant: at 390 the page keeps each table whole and scrolls it in its box. Boards B (a reservation's operations), C (subnets and options) and D (exclusions) are later steps.
Shots: desktop 1440 and 1280 (Subnets), 1440 (Leases, Reservations, Exclusions); phone 390 (each tab, and its first screen). Compared 2026-10-11.
Walked on the host 2026-10-11 (4f9a699, deployed 02:19 UTC): the DHCP reader's first read landed a second after the restart, both families answered (Kea 2.4.1), its store `data/readers/dhcp.json`; the page drawn from that stored document at 1440 and 390 shows what the capture showed: 6 subnets (3 IPv4 with ZTP's 255, 3 IPv6), 9 leases with IPv6 subnet 10 open on its three addresses for one DUID, 0 reservations. At 390 the tab strip scrolls sideways, as every v2 page's tabs do.
Compared again 2026-10-11 (C660: the operator asked whether the lab hosts' August reservations were missed). Kea's files on the host, counted read-only, hold none in any subnet or globally and no hosts database, so the 0 was true (C525 records their loss); the reader still drew 0 wherever Kea holds reservations outside a subnet's own list. It now reads the global ones and the subnets inside a shared network, says which reservations Kea uses in each subnet (reservations-global, reservations-in-subnet), and names a hosts database it does not read. On the lab's answer nothing drawn moved but the empty Reservations sentence, now "Kea's configuration holds no reservation, in any subnet that was read or at its global level".
Compared again 2026-10-11 (C529 step 3, board C's section 1): the Subnets table takes board C's columns (`DhcpSubnets.dc.html`, shot `dhcp-sub-c` at 1440 and 390, fed s1's committed intent and every subnet held by Mercury): Subnet with its Kea id under it, Pools as set, Gateway (3) with Kea's value against intent's VRRP address for the prefix ("matches intent", "intent says …", or that intent names none; ZTP's "none, by design (D4)"; IPv6 "from the routers' RAs" with each SVI's M and O flags from intent), DNS (6 / 23), the lease times, Leases now, Held by (Mercury, ZTP's posture, Kea's own file, or not known where Kea's files are not on this host); the note under the table says the move's state. Its Edit… and Remove… come with board C's operations; NetBox's VIP is not yet compared. Board A's other regions unchanged.
Templates compared: templates/v2/dhcp.html, templates/v2/_dhcp_view.html, templates/v2/_dhcp_reserve.html
Compared again 2026-10-11 after the subnet move (C529 step 5, run on the host): each subnet Mercury holds has board C's Edit… (its card: sections 2 and 3, the form, the change, Leases now, Checks, the confirm); ZTP's has none. Remove… and Add a subnet… are the next part. Walked on the host (2fbff36): the edit's preview against the live Kea named both leases a narrower pool would strand, each kept until its lease ends, and passed the gateway against intent.
Compared again 2026-10-11 (board C sections 4 and 5): Add a subnet… beside the heading with its (i), and Remove… under each subnet's Edit…, as board C draws them; the removal's card says the leases it ends service for and what survives, and asks the acknowledgement.
Compared again 2026-10-12 (C681, the operator's asks): each IPv6 lease's Identity cell carries its IAID under the DUID, and the shared-identity note says when the client asked with a new IAID each time and that a client installing its address "forever" keeps it whatever Kea's lease says, so a reservation is the fix (shot `dhcp-lea` at 1440 and 390). Board A draws the Identity column and the note's place; neither moved, so no region's verdict changed.
Compared again 2026-10-12 (C709, board C revised on canvas v117): each pool's description, held in Kea's `user-context`, is drawn under its range in the Pools column, and a pool Mercury holds with none says "no description: Edit… adds one" (shot `dhcp-sub-c` at 1440 and 390); the edit card's Pool description field sits beside Pool with the board's words under it (shot `dhcp-sub-c-edit`). ZTP's discovery pools say their client class's words, as the board draws them. **same**.
Compared again 2026-10-12 (the one stepper, C716), by its markup: board B's result draws the write path's five steps under What happened, and a confirm that failed draws them under its notice, whose first words follow the step reached (C723); every other region unchanged. The steps are the one stepper's component, compared with its boards in docs/fidelity/stepper.md; this record's shots hold no result state, so none was shot here.
Templates sha256: `2f3dbf925cc27d8b9991868abe365773b33415adb78e504b36c0fc51b62c7fd6`

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
| Subnets | subnet, Kea id, pools, lease times, in use of the pool, reservations; ZTP's marked with its discovery range | board C's columns since C529 step 3 (board C supersedes A's table): the Kea id under the subnet, a subnet's reservation count beside it, gateway, DNS and Held by added; the lab's ZTP subnet has no pool, said so | **same** (as board C's section 1; its Edit… and Remove… **later**, board C's operations) |
| Lease times' source | "from Kea's global level" | "the same as Kea's global" | **deviation** (log: DHCP's lease times are said to equal the global ones) |
| Reservations column | "2, in the tool's file for subnet 10" | the count; whose file is known after the move | **later** C529 step 2 |
| The subnets' note | "Every subnet is Mercury's" after the one host step | Kea's subnets are written by hand today, and the host step that moves them comes before Mercury's first change | **later** board C's host step (C529 step 2) |
| Leases | find by address, MAC, DUID or hostname; Every lease, Sharing an identity, Not in the inventory, Expiring within a day; groups by subnet, collapsed until opened | the same; a group opens by itself when flagged, searched or filtered, and a subset says how much of the whole | **same** |
| One client's several leases | together, "the same DUID" after the first, the DUID-LL read for its MAC, the drift said once beside them | the same | **same** |
| A managed device's lease | its device linked; "As the host holds it" read from the device, marked pending | the same, pending ("designed, not built") as the board marks it | **same** |
| "As the host holds it" | "not readable" for a host the tool does not reach, never blank; the note | the same | **same** |
| ZTP's leases | "3 asking, unknown: board L's list, Onboard › Discovered" (a link) | the count, and the Discovered list named in words, not built yet | **later** board L |
| Reservations | subnet, host, reserved by, address, Now (in use by it, unmatched with why, pending, no request yet) | the same columns and states, and "held by another client" | **same** |
| Reservations outside a subnet (C660) | not drawn: the board's Kea holds every reservation in a subnet | a global one as its own group ("IPv4, Kea's global level"), used only in subnets that turn reservations-global on; "not used" with Kea's setting named where Kea ignores one; a hosts database named above the tabs; a shared network's name beside its subnet | **deviation** (log: DHCP draws the reservations Kea holds outside a subnet) |
| Add, Edit, Remove | a button and a row's actions (board B) | not drawn; the note says they arrive next | **later** C529 step 2 |
| ZTP's reservations | "Open r8's plan" | not drawn: the lab's Kea holds none, and the plan page is onboarding's | **later** board M |
| Unmatched as Needs attention | a row naming the reservation, its action Edit… | not drawn: its action is board B's | **later** C529 step 2 |
| ZTP's subnet and board L | one store, two views: the Discovered list and this page | the ZTP group's line names the Discovered list | **later** board L |
| For the operator | how a reservation reaches Kea, the two ways | not drawn: the board's note to the operator, whose decision (option 1) is recorded in C529 | **same** |
| Exclusions | board D: named exclusions and the conflicts found | board D's sections (compared 2026-10-11 against DhcpExclusions in their empty states, as the lab is): Conflicts first (address, pool, assigned by, leased now, Exclude… opening the card with its reason from the source; "None found" when none); Exclusions with Add an exclusion…, each row's range, subnet, reason, source with who and when, in a pool or not, and Remove…; how each shaped pool is written to Kea; the card (section 4) in place. NetBox's addresses as a conflict source and the conflict's Needs attention row are not yet built | **deviation** (log: C529 step 3: board D's exclusions, where they live and how they are written) |

## Board B: a reservation's operations (C529 step 2)

Board: `DhcpReserve.dc.html` (board B, 1440), approved 2026-10-06 with board A. Shots: the board
at 1440; the page at 1440 and 390 with board B's three operations as previews (Edit h2's MAC,
Add an IPv6 address for h1, Remove h3's) and a refusal, against the lab's Kea answers with each
subnet's file of Mercury's (`tests/test_board_shots.py::test_dhcp_reserve`). Compared 2026-10-11.

| Region | Board | Built | Verdict |
|---|---|---|---|
| Entry points | board A: Add a reservation… on the tab; Edit… and Remove… on each row, Edit… primary on the unmatched one | the same; a row Mercury did not write (ZTP's, Kea's global level) says whose it is instead | **same** |
| The card's place | in place of the Reservations tab, the table below | the same | **same** |
| Header | the operation's title (Edit the reservation for h2 on 10.10.20.0/24); How does this work? | the same; Cancel in the header only until a preview can be confirmed | **same** |
| Fields | Reserved by (a select), the identity with a hint, Address, Hostname; "kept" under an edit's unchanged values | the same four, a Subnet select first for an Add (both families, ZTP's left out); Preview to ask Kea | **same** |
| Change | the subnet and reservation named, then − and + lines, wrapped | the same, under the fields in one part (a removal's in its own) | **same** |
| Checks | pass, note: inside the subnet and its pool; no other reservation names it; Kea's own check; the file's version | the same, and the stranded check (every place Kea holds reservations); Kea's own check marked "at confirm" | **deviation** (log: Kea's own check runs at confirm) |
| Not done / What survives | the lease kept until the client asks again; other leases named, not removed; a removal's lease and the repository's history | the same, from Kea's leases | **same** |
| Footer | Recorded on confirm…; the reason; Cancel; the primary, disabled until a reason is given | the same; the reason field required, so an empty one is refused by the browser, the button not drawn disabled | **deviation** (log: A required reason, as Reload's) |
| Result | done, What happened (read back), Recorded (commit, Actor, Source) | the same, in place; What happened leads with the one stepper's five steps (2026-10-12), and a failed confirm draws them under its notice, which says "Nothing was changed" only while true (C723) | **deviation** (log: the one stepper: results of one-request operations drawn as steps) |
| Refusal | Not reserved, the comparison and both operands, when Kea was read | the same, inside the card under the fields, so the person corrects and previews again | **same** |
