# Fidelity: Troubleshooting in the sidebar, and Troubleshooting › Incidents (board T)

**Provisional, operator review pending** (the operator, 2026-11-13: "GUI boards: approved
provisionally for initial implementation and testing (board R, board T the Troubleshooting
sidebar, review items)"). The sidebar's Troubleshooting section and the incidents list as
built, compared region by region with board T
(`~/Documents/nmas-reports/boards/troubleshooting-nav.html`: part 1, the sidebar before and
after; part 2, what each item opens; part 3, where every screen goes; part 4, Incidents › Open
as it would first draw), the GUI review's proposal 17 and finding IN9
(`~/Documents/nmas-reports/gui-review.md`). Compared by the templates against the board's
parts and the pages tests/test_incidents_list_v2.py draws (the incident page's three planted
fixtures together on one network, and 900 incidents), not from board shots: the board is not
on the mockups canvas, so tests/test_board_shots.py has no file for it yet. A shot comparison
at 1440, 1280 and 390 is the operator's review's. The incident page's breadcrumb is compared
in `incident.md`.
Compared 2026-11-13.
Templates compared: templates/v2/incidents.html, templates/v2/_incidents_chip.html, templates/v2/base.html
Templates sha256: `e29f14af964c1849d12616ab0e78bb32a878176ce016ea96c14d55f0145d4827`

Compared again 2026-11-14 00:5x UTC: each group's disclosure gained its `data-keep` key (so a
live redraw keeps an opened group open, C472) and a template comment's words; no region drawn
differently, every verdict below unchanged (provisional, operator review pending).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar: the section's place | TROUBLESHOOTING above OBSERVE, after History | the same | **same** |
| Sidebar: Incidents | the item, its count of open incidents outlined ("3 open"), Needs attention keeping the one red badge | the same; "…" until the count arrives, "?" outlined dashed when a store cannot be read | **same** |
| Sidebar: Incidents' tabs row | "Open · Closed · Problems" under the item | "Open · Closed", each a link to its tab | **deviation** (log: Board T built: only what has a page is drawn) |
| Sidebar: Self-healing | the item, the network's mode as its chip ("Dry run"), moving the policy to its own page | the item and its chip (Off, Dry run or Auto, the policy's sentence on hover), opening the network's Self-healing tab in Settings | **deviation** (log: Board T built: Self-healing opens Settings' Self-healing tab) |
| Sidebar: Self-healing's sub-pages row | "Overview · Fix kinds · Saved fixes · Runs · Holds" | not drawn | **deviation** (log: Board T built: only what has a page is drawn) |
| Sidebar: Drills and Reports | two items, "suggested" | not drawn | **later** each with its own page, on the operator's decision (d) |
| Incidents: the bar | "Incidents", tabs "Open · 3", "Closed · 41", "Problems · 2", "checked 20 s ago" | the heading with its (i), tabs "Open · N" and "Closed · N", "checked" with the read's age | **deviation** (log: Board T built: only what has a page is drawn) |
| Incidents: the summary | "3 open · 1 needs a person · 1 Mercury working · 1 watching" | the same words, each group's count, the empty ones left out | **same** |
| Incidents: the rows' arrangement | one flat list, a row per incident | one closed-or-open details per group, 50 rows each, the rest counted | **deviation** (log: Board T built: Incidents' rows grouped and collapsed) |
| Incidents: an Open row | the state's dot and word, the title and its next step, since, Open incident | the state's badge (Drill beside it for a drill), the title as the link, the device and what it waits for, since | **deviation** (log: Board T built: a row's title opens the incident, and its next step is what it waits for) |
| Incidents: a Closed row | how it closed, time to repair, by whom | the group says how it closed; the row its state, title, device, fixed by whom, time to repair and when it ended | **same** |
| Incidents: filters | Closed: filter by device, kind, outcome | a search over title, device and id and a device filter, on both tabs; the outcome is the groups | **deviation** (log: Board T built: Closed filters by device and words, its outcome the groups) |
| Incidents: Problems | the suggested third tab, recurring faults by fingerprint | not built | **later** the Problems tab, on the operator's decision (b) |
| Incidents: nothing acts | "nothing on this list acts on a device" | the same: three GET routes, links only | **same** |
| Incident detail: its address | `/v2/incident/<id>?list=<net>`, unchanged | the same | **same** |
| Incident detail: its breadcrumb | Incidents › Open (or Closed) › the title | Incidents / Open (or Closed) / the title, in the app's crumb separator; the sidebar marks Incidents current on it | **same** |
| Needs attention | stays the inbox, its items linking each incident's page | unchanged | **same** |
| Device pages' Incidents tab | the device's incidents, the same rows filtered | not built | **later** a device-page tab, its own mockup |
