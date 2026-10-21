# Fidelity: Source of truth › NetBox

The NetBox page as built (the connection, every network with its last import and removals, and
the job card each Import into NetBox…, Remove from NetBox…, Stop tracking instead… and Import
every network… fills in below the table), compared region by region with its boards (C650's
step), after the operator's walks W2 (2026-10-16, steps 16 to 20, on Default) and W3
(2026-10-17, steps 13, 20 to 23, on Default and the throwaway network W3 walk). No shot test
exists for this page (tests/test_board_shots.py has none), so the page as built is the
operator's captures: W2's 10 (phone width), 11 (desktop, before the import) and 12 (the import
preview filling in, with In progress open); W3's 10 and 11 (Remove from NetBox for a network
with no record), 18 to 20 (Default's import preview, "NetBox already matches"), 21 and 22 (the
import's busy state and its result), 24 (Remove's preview, "Remove is not offered") and 25
(Stop tracking's preview). The regions no capture holds are compared by the template, said
in the row.

Boards: no board file exists for the page itself. The 2026-10-10 line of
docs/STANDING_APPROVAL_LOG.md, "Board: Source of truth › NetBox", is its board (the connection
and master switch; every network's devices, last import and removals with Import into
NetBox… and Remove from NetBox…; Import every network…; a job card that fills in), drawn and
counted as signed off under the Phase 7 mode. C954's board `NetboxStopTracking.dc.html`
(the 2026-10-16 line "Board: NetBox's Remove card gains Stop tracking instead…") is not in the
local copy of the canvas this record was read beside, so its region is compared with that
line's words. `redesign/NetBoxBrowser.dc.html` and `redesign/PhoneNetBox.dc.html` are the
device page's NetBox browser (tab:netbox), not this page.
Shots: the operator's captures above; no board shot (no board file).
Compared 2026-10-17; the job card's Free <address> from <record>… (C1504) compared by the
template and its tests 2026-10-21, no capture or board shot.
Templates compared: templates/v2/netbox.html, templates/v2/_netbox_job.html
Templates sha256: `e3f8d445492d10a6b1d8ce3c47e9c057d6df958b33f6e13bb004179bba774a57`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | NetBox under SOURCE OF TRUTH | NetBox current under SOURCE OF TRUTH (every capture) | **same** |
| Page head | not drawn by the line | "NetBox" with its (i), and the sub-line "Import a network's devices into NetBox from their committed golden configs, or remove what Mercury created there. Each is previewed against the real NetBox and confirmed once; nothing is sent to a device." (W2 capture 11) | **same** |
| Connection | the connection and the master switch | the card "Connection", badged "answering", the version, and "Writes are on for every network; they are turned off on Settings › Installation's NetBox card." The switch is not a control here: it is turned off on Settings › Installation, and turned on only by a confirm below while writes are off (compared by the template) | **deviation** (log: NetBox: the master switch is words here, set on Settings › Installation and by a confirm) |
| Networks table | every network's devices, last import and removals | "Networks" with its count ("1 network", "2 networks"), the columns Network, Devices, Last import, Removals; Last import a badge ("complete"), the run's summary and its time; Removals "none" (W2 capture 11, W3 capture 10) | **same** |
| Last import after an import | not drawn | after W3's import (capture 22) the row still read the previous import's time, 2026-10-16 22:53:18 (C1117) | **deviation** (log: NetBox: Last import keeps the previous time after an import (C1117)) |
| A network's buttons | Import into NetBox… and Remove from NetBox… per network | the two, each with its (i); Import greyed for a network with no devices (W3 walk, 0 devices, its reason on hover; W3 capture 10) | **same** |
| Import every network… | one control for every network | in the card's head with "How does importing every network work?" (W2 capture 11); its card headed "every network" while its summary says "every device list" (C1017) | **deviation** (log: NetBox: Import every network's card is headed every network, its summary every device list (C1017)) |
| The job card, filling in | a job card that fills in | "Import into NetBox: Default" with Close, its steps (Region, site and template; Each device read and planned; Cables between devices; The preview) as the one stepper with the step's time, and "A dry run of the real import against the real NetBox, writing nothing. This card fills in when it is ready." (W2 capture 12) | **same** |
| The preview's list | the plan's writes | "What will be written to NetBox", each line drawn one word wide down the card (W3 captures 18 to 20, and Remove's and Stop tracking's lists in 24 and 25; C1115) | **deviation** (log: NetBox: the job card's lists are drawn one word wide (C1115)) |
| The preview's counts | the plan's summary | List, Devices, Creates, Updates and Plan hash (Deletes, Left alone and Taken with them for Remove; Forgets, By type, Deletes in NetBox for Stop tracking) drawn as a stacked list, each value indented under its name, unlike the facts grid of every other v2 card (W3 captures 20, 24, 25) | **deviation** (log: NetBox: the preview's counts are a stacked list, not the cards' facts grid (a defect, register C650 follow-up)) |
| A preview that changes nothing | not drawn | "Import Default (9 device(s)): nothing to create or update. NetBox already matches." over 9 "update … changes nothing (sent; every value already held)" lines, Updates 9, and Import offered (W3 captures 18 to 20; C1041, C1118) | **deviation** (log: NetBox: a no-op import lists 9 updates and offers Import (C1041, C1118)) |
| The gates | checked at preview and at confirm | "Checked now, and at your confirm": each gate with its badge (passed, at confirm, not established, not applicable) and its words; the "not established" and "not applicable" badges run into their text (W3 captures 24 and 25; C1116) | **deviation** (log: NetBox: the not established and not applicable badges overlap their text (C1116)) |
| What it does not do, and the confirm | the confirm | "What it does not do" as bullets, then Import with "How does confirming work?" and "You are confirming as <you>. The plan is recomputed at your confirm; if NetBox moved, nothing is written." (W3 capture 20) | **same** |
| Busy on the confirm | not drawn | "Starting the import…" on the button itself until the result drew (W3 capture 21; C1023 fixed) | **same** |
| The result | the job card's result | "9 of 9 device(s) imported into NetBox (0 created, 9 updated): everything landed.", ticked, with what was not imported on purpose and why, in place of the preview (W3 capture 22) | **same** |
| Remove from NetBox, nothing recorded | the removal's preview | "Remove from NetBox: W3 walk": "Mercury has no record of creating anything in NetBox for this list, so there is nothing safe to remove…", Deletes 0, its gates (W3 captures 10 and 11) | **same** |
| Remove from NetBox, a cascade not measured | the removal's preview and confirm | the deletes listed, "Remove is not offered: what NetBox's database takes with each of the 9 delete(s) must be established, and 3 answer(s) could not be…", Read again, and no Remove button (W3 capture 24; C932) | **deviation** (log: C932 (B9): Remove from NetBox is offered only when what every delete takes with it is established) |
| Stop tracking instead… (NetboxStopTracking) | its own preview: deletes nothing in NetBox, Mercury forgets N objects it created, each named, counts by type, where the data survives; Stop tracking the one confirm | "Stop tracking instead…" under Remove's card with its line; its preview lists each object forgotten, Forgets 10 and By type, "Deletes in NetBox 0", its gates, What it does not do naming where the data survives, and Stop tracking with "How does stopping tracking work?" (W3 capture 25; not confirmed in either walk) | **same** |
| Removals column | removals recorded per network | "none" for both networks; a network with removals links "N recorded", opening the removal record in the job slot (compared by the template and `_netbox_removals.html`; neither walk had one) | **same** |
| Free an address a retired record holds (C1504) | not drawn: no board drew it; drawn under the operating mode | on an import's preview, a warning per device address a Decommissioning record holds ("<address> is held by <record> (NetBox device N, Decommissioning)…") with Free <address> from <record>…; its own preview in the same card, headed "Free <address> in NetBox from <record>", each write by object and id, Record, Status, Address, Deletes, Unassigns and Plan hash, its gates, and Free <address> (busy Freeing…) behind the same writes box; its result in place, then Preview the import of <device> again… (compared by the template and tests/test_free_held_address.py, no capture) | **deviation** (log: NetBox: an import's preview offers Free <address> from <record>… (C1504)) |
| Phone width | not drawn | the cards stacked; the Networks table in its own scroll, Last import a narrow column, and the second (i) beside Remove from NetBox… cut at the screen's edge (W2 capture 10; C1043) | **deviation** (log: NetBox: at phone width the second (i) is cut at the edge (C1043)) |
