# Fidelity: Onboard devices › Discovered (board L)

The Discovered page as built, compared region by region with its board. Read from shots of the
board and the page side by side, in the same headless Firefox, the page fed by the discovery
reader's value built by the reader's own `shape` from the lab's captured Kea (pools as Kea
reports them after the host step) with three devices asking, one picked and one gone quiet
(`tests/test_board_shots.py::test_onboard_discovered`).

Boards: `ZtpDiscovery.dc.html` (board L, 1440 wide) on the mockups canvas, redrawn 2026-10-11 from NSOT_STAGE7_PLAN 16's measurements (canvas version 111) and signed off under the Phase 7 mode. Board M (`ZtpPlan.dc.html`, the plan a Pick leads to) is a later step.
Shots: 1440, 1280 and phone 390 (the page and its first screen). Compared 2026-10-11.
The range it reads was installed on the host 2026-10-11 21:16 UTC (5cbb226, the host step 10 of 10 PASS); after it, the lab's unreserved hosts renewed through their relays still got 365 days.
Templates compared: templates/v2/onboard.html, templates/v2/_onboard_discovered.html
Compared again 2026-10-11: each group carries `data-keep`, so a live redraw keeps it open or closed as the person left it (C472); nothing drawn moved.
Templates sha256: `bbceab85692b1411559f4931d16d96be9b0340fd447c1ed221d23ab5db6f4743`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Devices current | the same | **same** |
| Breadcrumb | Devices › Onboard devices › Discovered, the first two links | Devices a link; Onboard devices plain (it has no page of its own yet) | **later** board M (the Plan devices page) |
| Header | the title, How does this work? at the right | the title with its (i), as every v2 page (C505) | **same** |
| Tabs | Plan devices, Discovered (3), Pending (2) | Plan devices (opens Devices, where Add device… is) and Discovered with its count; no Pending tab | **deviation** (log: board L's tabs) |
| Summary | the three counts; not listed: reserved, in the inventory | the three counts; not listed: MACs already reserved, onboardings waiting with a MAC | **deviation** (log: board L's "not listed") |
| The range | its prefix, every 30 s, its age; five minutes, no boot file, router or DNS; two pools | the same, the pools as Kea reports them; a range Kea runs not, or only in part, said first | **same** |
| Filter and search | a search box and a vendor drop-down | three vendor buttons and a search form (each a link or a form that works without script), the subset said | **deviation** (log: board L's filter) |
| Asking now | MAC, vendor class, client-id, hostname, board serial, its lease, asking since, last asked, next request (its cadence), Pick | the same columns but the board serial | **later** the board serial (the client-id's serial form, read when Kea's lease holds it) |
| Pick | an inline card under the row: name, platform, role, interface, address, site, which way in; "Plan r8's first boot…" | Pick… opens Add device in place above the groups, with the MAC and the ZTP way (board E's form, its review and Create) | **deviation** (log: board L's Pick) and **later** board M |
| "Asking now" words | a request within the lease time | a request in the last 10 minutes (two leases, so a late renewal does not move a device to quiet) | **deviation** (log: board L's groups) |
| Picked, not taken | MAC, picked as, asking since, picked (by whom), since the Pick (offers counted), now, Reload r9's host… | MAC, picked as (a link), asking since, picked, now; the reload and the withdrawal said, not buttons | **deviation** (log: board L's groups) and **later** the Reload button |
| Gone quiet | MAC, client-id, asking since, last asked, now | the same | **same** |
| The clock note | the cadence read from its own gaps | the same, under Asking now | **same** |
| The two refusals | serial shared; a name planned with another MAC | made by Add device's review (a name in use is refused there); serial ways are board M's | **later** board M |
| Measured note | the C8000v's option 60 and 61, the serial's instability | the same, shorter | **same** |
