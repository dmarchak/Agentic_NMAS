# Fidelity: the device page's Overview tab

The Overview tab as built, compared region by region with its boards (C650's step). Read from
shots of the boards and the page side by side, in the same headless Firefox
(`tests/test_board_shots.py::test_tab_overview`), on the browser layout test's lab
(`tests/test_profile_apply.py`'s: r2's real captured configuration as its golden and its parsed
intent committed; r6 in its real shape), r2 and r6 answering in the reachability store; then r6
with `cdp run` in its golden and not in its intent (`tests/test_overview_intent.py`'s case), the
state in which the difference is drawn. No drift run, startup check or alert reader is stored in
the lab, so those checks are drawn in their "no record" words. The page's header, tab strip and
Actions menu are the device page's own record (`device.md`); this record compares the tab's body.
The operator's walk W1 (2026-10-16) opened every device page on this tab (the operator's W1
captures 09 and 31 show the tab strip with Overview current, a card drawn in its place); no
capture shows its body, so the shots alone are compared here.

Boards: `Device.dc.html` ("Device page: r3, Actions open", 1440 wide; its content under the
tabs) and `DevicePhone.dc.html` ("Phone: r3", 390), canvas page "Landing, devices, device";
`DeviceOverviewFolded.dc.html` ("Device page: edge1, empty tabs folded", 1440) and
`PhoneFolded.dc.html` ("Phone: edge1, tabs folded", 390), canvas page "Services"; all on the
"NMAS redesign mockups" canvas, signed off as NSOT_GUI_BRIEF section 13 (2026-09-29) and the
services review with its tab rule (section 14.1, 2026-09-30).
Shots: `tab-overview-board-1440`, `-1280` beside `tab-overview-page-1440`, `-1280` (r2);
`tab-overview-board-390` beside `tab-overview-page-390` and `-390-first`;
`tab-overview-folded-board-1440` and `-390` beside `tab-overview-folded-page-1440` and `-390`
(r6, the difference drawn; every tab still drawn).
Compared 2026-10-16.
Templates compared: templates/v2/_overview.html, templates/v2/_drift_detail.html
Templates sha256: `7b80cb8910a644780954a4e977632d407d1dea3bb653810de745de17fe1f3a7f`

Compared again 2026-10-16 (C532) after `_overview.html` gained an Intent state row under Last
measured: the Devices list's state for this device, from the one function both draw
(`device_list.intent_state`), saying it is the list's, from the last measurement, and that the
Intent check compares now; the tab redrawn on golden, intent and template commits as well. Shots
`tab-overview-page-1440`, `-390` (r2: "intent changed since measured", its intent committed after
its onboarding golden, beside the Intent check's live "matches its committed intent") and
`tab-overview-folded-page-1440` (r6: "departs (-1)" beside the check naming `cdp run`). The
Intent state region added; no other region's verdict changed.

Compared again 2026-10-16 (C342) after the Drift row gained what it opens onto, built from board
`C342Drift.dc.html` ("The device page's drift: the lines, the log and three choices", 1440, its
phone column at 390; drawn by the agent and counted as signed off under the Phase 7 mode, logged
in docs/STANDING_APPROVAL_LOG.md), with the new fragment `_drift_detail.html` compared with it.
Shots (`tests/test_board_shots.py::test_tab_overview_drift`, on test_device_v2's lab: the real
drift run over r2's real configuration with one description and the account's password edited,
s3's real syslog lines as r3's): `tab-overview-drift-board-C342Drift-1440` beside
`tab-overview-drift-closed-page-1440`, `-1280`, `-390`, `tab-overview-drift-open-page-1440`,
`-1280`, `-390` and `tab-overview-drift-unreadable-page-1440`, `-1280`, `-390`. Board (a), at
golden, is the Checks: Drift row above, unchanged. The Drift regions below were added; no other
region's verdict changed.

Compared again 2026-10-26 (C1819, the operator's Walk 3: "Drift: clean at the last run" sat
above "Intent: departs (+1 -1)" after a Capture took in a console change) after the Drift row
was renamed for what it measures, **Since last capture** ("unchanged at the last run",
"changed: differs from its golden by N line(s)"), and gained a warning when the last capture
took in a change made outside Mercury that departs from intent. No template changed (the row's
name and words come from `device_page.drift_row`), so the hash stands. Shots
(`tests/test_board_shots.py::test_tab_overview_drift`): `tab-overview-drift-board-C342Drift-1440`
(opened, and it is board C342Drift: boards (a) to (e) under its sign-off note) beside
`tab-overview-drift-closed-page-1440`, `-1280`, `-390`, `-open-`, `-unreadable-`. The flagged
state has no shot: it is read from the page as the route draws it
(`tests/test_out_of_band_capture.py`, `TestNoCheckReadsClean`). The Checks: Drift and Drift,
closed regions' verdicts moved to deviation; no other region's verdict changed.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The tab's help | an Info link on each card | one (i) "About this tab" above the cards, as on every v2 tab | **deviation** (log: Device Overview: one help link for the tab) |
| Layout | three record cards in a row (Committed intent, The device, The difference), Checks under them in two columns | two cards side by side: Around this device (the records as rows) and Checks (one column); one column at phone width | **deviation** (log: Device Overview: the records as rows of one facts card) |
| Committed intent | commit sha, age, by whom; `host_vars/r3.yml` and what it holds (4 interfaces, OSPF 1, BGP 65003, syslog block) | the commit sha, age, Source and Actor; "none committed … not deployable" without one; the profile commit it inherits on its own row; what intent holds is not summarised | **deviation** (log: Device Overview: the intent's summary line is not drawn (a defect, register C650 follow-up)) |
| The device | captured when, recorded as golden sha; "A golden is a record of the device, not a target" | Golden (sha, age, Source, Actor) and Last measured (when, by which operation); the card's foot "A golden is a record of what the device runs; intent is what it should run" | **same** |
| The difference | "None: r3 is at its intent", compared on the capture of 28 min ago | the Intent row of Checks: "matches its committed intent", or warn naming each line on the device and not in intent (r6's `cdp run`) and the reverse | **deviation** (log: Device Overview: the difference drawn as the Intent check) |
| Intent state (C532) | "None: r3 is at its intent", compared on the capture of 28 min ago, inside The difference; the header's "At intent" chip (the device page's own record) | a row of its own: the state's chip (the Devices list's, the same function), when intent moved and what the measurement read where it has moved, and the words saying the Intent check compares now | **deviation** (log: Device Overview: the recorded intent state is a row of its own (C532)) |
| Address, model, platform | in the page's header only | also as rows here, each with its source (the golden's Chassis type line, the inventory) | **same** |
| Checks: Drift | "Drift: clean at the last run", against its golden, and when | "Since last capture: unchanged at the last run" with its time; "no drift run recorded for this list" where none is (the lab); a warning, never a pass, when the last capture took in a change made outside Mercury that departs from intent, naming the capture's commit and how the device's log says it changed (C1819) | **deviation** (log: Device Overview: the Drift check is named Since last capture (C1819)) |
| Drift, closed (C342, board b) | the row's words and time, and "The lines, what r3's log says, and what to do" to open | the same, its words "Since last capture: changed: differs from its golden by N line(s)", the disclosure opening in place and asking once (a read); kept open across a redraw | **deviation** (log: Device Overview: the Drift check is named Since last capture (C1819)) |
| Drift, open: the lines (C342, board c) | the counts only on r3 and only in its golden, the run that kept them and whether the last run counted the same; the diff masked; how many lines masked; the golden's sha | the same words and parts; the run's times as ages with the time on hover; the diff drawn whole as the run kept it (its own row below) | **deviation** (log: Device Overview drift: the run's times are ages, the clock time on hover) |
| Drift, open: the diff's extent (C342, board c) | two hunks, one context line each | the unified diff as the run kept it: its header, three context lines each side, the run's own note when comment lines differ | **deviation** (log: Device Overview drift: the kept diff is drawn whole) |
| Drift, open: the log (C342, board c) | each configuration or restart line at its receive time, the device's own time on hover; the window's words; Every line from r3: its Logs tab | the same; each receive time with its date | **deviation** (log: Device Overview drift: each log line's receive time carries its date) |
| Drift, open: what to do (C342, board c) | Keep it: Capture with "How does capture work?"; Put intent back: Plan a deploy… (i); Remove lines: Remove lines (Mode B)… (i); each with its words, capture first for the last two | the same controls, words and links, each opening its card in place of the tab as the Actions menu does, carrying the network | **same** |
| Drift, a source that cannot answer (C342, board c2) | "Not kept: …" for lines no longer kept; "Couldn't load: …" for Loki | the same, each in its part, the rest drawn; Loki not configured says so in its own words | **same** |
| Drift, unreadable (C342, board d) | its own mark, the word unreadable, the reason, whether r3 is at its golden not known; nothing to open; apart from never run | the same, the mark the warn icon in grey | **deviation** (log: Device Overview drift: the unreadable mark is the warn icon in grey) |
| Drift, phone (C342, board e) | one column, the open row's parts stacked, each choice's words under its button, the diff scrolling in its box | the same | **same** |
| Checks: Freshness | Oxidized holds the approved config | not drawn: Oxidized's freshness reader was switched off 2026-10-08 (`reader_job.RETIRED`) with Oxidized's retirement, so no source exists | **deviation** (log: Device Overview: no Freshness check, its source retired) |
| Checks: Heartbeat | last seen 3 min ago, its window 12 min | not drawn on the Overview (the heartbeat is the Logs tab's line and Monitoring's alert) | **deviation** (log: Device Overview: no Heartbeat, Last deploy or Neighbours check (a defect, register C650 follow-up)) |
| Checks: Last deploy | verified 2 days ago, BGP held 180 s, receipt 38 | not drawn | **deviation** (log: Device Overview: no Heartbeat, Last deploy or Neighbours check (a defect, register C650 follow-up)) |
| Checks: Neighbours | OSPF 3 full, BGP 1 established, with r5 outside management | not drawn (the Neighbours tab holds them) | **deviation** (log: Device Overview: no Heartbeat, Last deploy or Neighbours check (a defect, register C650 follow-up)) |
| Checks: Reboot-safe | the startup config carries its credential, and when | the hourly startup check's row, or "has no row for it" (the lab) | **same** |
| Checks: Credential and Alerts | not drawn | Credential (rotation and policy) and Alerts (Grafana's firing alerts for the device, or that no reader has written them); with no reader the Alerts row names the reader's file by its full path on the host ("no reader has written /…/readers/grafana-alerts.json") | **deviation** (log: Device Overview: the Credential and Alerts checks) |
| Around this device (folded board) | the DHCP lease, NetBox, Neighbours, Prometheus, Syslog and Oxidized lines, each in one line with its time | the records' rows only: no DHCP lease, NetBox, Neighbours, Prometheus or Syslog line | **deviation** (log: Device Overview: empty tabs are not folded into the Overview (a defect, register C650 follow-up)) |
| Tabs folded | six tabs for edge1: a tab with nothing to show is not drawn, "Why some tabs are not shown", the footnote "Six tabs, not eight" | all eight tabs drawn for every device (`device_v2.BUILT`; the walk's captures show the eight on every device); the rule signed off 2026-09-30 (NSOT_GUI_BRIEF 14.1) is not built | **deviation** (log: Device Overview: empty tabs are not folded into the Overview (a defect, register C650 follow-up)) |
| Check marks | a green check per passing row; the folded board's "passed" at the right | the check's icon by state (ok, warn, danger, unknown as a dot) and the result's time at the right | **same** |
| Phone | The difference and Checks only, one column | both cards, one column, every row; the facts card first | **deviation** (log: Device Overview: the records as rows of one facts card) |
