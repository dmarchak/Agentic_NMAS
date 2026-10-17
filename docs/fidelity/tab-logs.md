# Fidelity: the device page's Logs tab

The Logs tab as built (`/v2/device/<name>?tab=logs`: what the device sent to syslog as Loki
holds it, newest first, heartbeats folded), compared region by region with its board (C650's
step), from the operator's walk W2 (2026-10-16, step 58: r6's Logs after its reload, read for
its boot lines). No shot test exists for this tab (tests/test_board_shots.py has none), so the
page as built is the operator's W2 capture 70 (r6's Logs tab, 14 lines visible of 100). The
device page's shell (crumbs, header, Actions, tabs) is compared in docs/fidelity/device.md.

Board: `redesign/DeviceLogs.dc.html` ("Device: Logs", 1440), on "NMAS redesign mockups", the
Services mockups NSOT_STAGE7_PLAN 1g signed off on 2026-09-30. `redesign/PhoneLogs.dc.html` is
the sidebar's Logs page at phone width, not this tab.
Shots: the operator's capture above; the board at 1440, rendered in the same headless Firefox
(no shot test to run it).
Compared 2026-10-17.
Templates compared: templates/v2/_logs.html
Templates sha256: `b5c9be412875294ecddb0f95be6aa9d25ad1e21c081c4651132a7fc4824ec3c0`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The tab | Logs current among Overview, Intent, History, Monitoring, Logs, NetBox, Neighbours, Ask the device | the same eight, Logs current (capture 70) | **same** |
| The tab's help | not drawn | the (i) "About this tab" at the card's corner (capture 70) | **same** |
| Range | 1 h, 24 h, 7 d | none: always the last 24 h | **deviation** (log: Device Logs: no range, kind or severity filter) |
| Kind | Syslog and traps, Syslog, Traps | none: syslog only, no trap drawn | **deviation** (log: Device Logs: no range, kind or severity filter) |
| Severity | All, 0 to 4, 0 to 2 | none | **deviation** (log: Device Logs: no range, kind or severity filter) |
| Open in Logs, as a query | a link to the Logs page with the tab's query | none: the tab names neither the Logs page nor History › Query (W2's findability question 24, "the traps s2 sent today", not found: C1071) | **deviation** (log: Device Logs: no link to the device's lines on Logs or History › Query (a defect, register C650 follow-up)) |
| Heartbeats | "Selected by r3's own name in each line (the origin-id)… 288 heartbeats in 24 h, the expected 288." | "281 heartbeat(s) in the last 24 h, the last 11 min ago. They are folded here; any other line about the heartbeat applet is listed below." with a tick, or a warning when none came; no expected count; the origin-id note at the card's foot (capture 70) | **deviation** (log: Device Logs: heartbeats counted without the expected count) |
| The card head | "412 lines in 24 h, newest first" and "answered in 180 ms" | no count and no answer time; a cut list says "Showing the newest 100 of the last 24 h; older lines are in Loki." (capture 70) | **deviation** (log: Device Logs: no line count or answer time; a cut list says so) |
| The device's clock | not drawn | "46 line(s) carry a device time r6 marks unsynchronised (*): its clock is not trusted, so each line is placed by when Mercury received it." and the * beside each such time (capture 70) | **same** |
| Columns | Time (UTC), Severity, Kind, Line | Received (an age, the time on hover), Severity, Message, Device time (capture 70) | **deviation** (log: Device Logs: Received and the device's own time, no Kind column) |
| Severity | the number and the word ("5 notice"), neutral | the word alone in its level's colour ("notice", "warning" amber, "error" and "critical" red); a link coming up, sent at level 3, drawn "error" in red (capture 70; C1069) | **deviation** (log: Device Logs: severity is a coloured word, the device's own level (C1069)) |
| The line | the line in mono | the mnemonic in mono, then the text (capture 70) | **same** |
| A line holding an account | masked ("[user: <redacted:user>]") with Reveal… | drawn as sent, the account's name and the source address in the line (capture 70); no Reveal. The account's name is not a secret here: the device header names it on every tab ("signs in as …") | **deviation** (log: Device Logs: a login line shows its account's name, unmasked, with no Reveal) |
| Loki not configured, or not read | not drawn | "Loki is not configured, so r6's logs cannot be read here", or the error with "Not the same as r6 having sent nothing." (compared by the template) | **same** |
