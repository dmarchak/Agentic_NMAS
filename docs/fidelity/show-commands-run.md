# Fidelity: Show commands, a run's page (C548 boards C, C2, D, F's result, E and G)

A Show commands run's page as built, compared region by region with its approved boards (C650's
step), after the operator's walk W1 (2026-10-16, step 6: the logging path tested on s1 and r1,
both received). Read from shots of the boards and the page side by side, in the same headless
Firefox (`tests/test_board_shots.py::test_show_commands_run`), every run started through the real
route on Show commands' lab (tests/test_show_commands.py: r3 IOS-XE and r9 IOS, the sessions faked
at the connection seam answering from real captures): `show clock` and `show ip interface`
(alike and not); C2's OSPF captures (r9's IPv6 answer empty) as opened, with Dead Time ticked
through the real route, and against r3 with only the differences; r3 and r9 side by side; a run
with r3's `show ip interface` failing (planted, a TimeoutError), its `show logging` past the cap
(s1's real capture repeated past 32 KiB) and r9 held by another operation (a real hold); and a
logging-path test with board F's Loki stand-in (r3's line arrives, r9's never; the wait
shortened to 1 s). Two devices where the boards draw five or nine. Read beside them: the
operator's W1 capture 07 (the logging path on 2 devices, done, "2 received", r1 after 0.4 s and
s1 after 1.2 s), at about half desktop width.

Boards, on the NMAS v2 mockups canvas, page "C547/C548: Ask the device and Show commands"
(approved 2026-10-08; signed off in tests/signed_off_screens.py: "C548 boards C, D and E (canvas
page 'reads'), signed off 2026-10-08: the summary, the groups, side by side and only the
differences"): `ReadsFleetResult.dc.html` (C, 1440: the summary, answers grouped and collapsed,
a device's answer cut at the cap), `ReadsResultC2.dc.html` (C2, 1440: the result revised, C577
to C580; it supersedes C where they differ), `ReadsCompare.dc.html` (D, 1440: side by side, only
the differences; its region 12 is History's row), `ReadsLogPath.dc.html` (F, 1440: its regions
7f to 8g, the test running and its result), `ReadsReasonC582.dc.html` (its region 4, the run's
record naming the reason), `ReadsPhone.dc.html` (E, 390: its second part, a fleet result) and
`ReadsLogPathPhone.dc.html` (G, 390: C2 and F at phone width).
Shots: `show-commands-run` (C beside the page at 1440 and 1280, E beside it at 390),
`show-commands-run-failed` (1440), `show-commands-run-c2` (C2 at 1440 and 1280, G beside it at
390), `show-commands-run-c2-ignored` and `-c2-against` (1440), `show-commands-run-compare` (D at
1440, the page at 1440 and 390), `show-commands-run-logpath` (F at 1440, the page at 1440 and 390).
Compared 2026-10-16.
Templates compared: templates/v2/show_commands_run.html, templates/v2/_sc_result.html, templates/v2/_lp_result.html, templates/v2/_run_stepper.html
Templates sha256: `f2f90f7d588b3e264fd8dc963bd4977390c0bba2606f6a10f4cdcb23c00dd9e1`

Compared again 2026-10-17 (C1023) after Group again (`_sc_result.html`) and Test again and "Test (device)
again" (`_lp_result.html`) became busy on themselves while their request is out
("Grouping again…", "Starting the test…"). At rest the page draws the same words. Compared by
the template and the page the tests draw (tests/test_v2_busy_on_itself.py), not a new shot; no
region's verdict changed.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Crumb | "Show commands › today 15:58 UTC" (C2), the command after it on D | "Show commands › 2026-10-15T23:40:13Z": the run's time drawn as its raw ISO value (capture 07 and every shot) | **deviation** (log: Show commands run: the crumb draws the run's raw timestamp (a defect, register C650 follow-up)) |
| Header | the result card leads | "Show commands" with the (i), "Default: one run's answers, grouped where they are the same." over the card, as every v2 page (capture 07) | **same** |
| The result's head | "1 command on 5 devices", done; Run again, Save as a set…, How does this work? | "2 commands on 2 devices", done; no Run again, no Save as a set…, no How does this work? on the card | **deviation** (log: Show commands run: the result has no Run again or Save as a set (a defect, register C650 follow-up)) |
| By and when | "By <operator>, 15:58 UTC (09:58 UTC−6), 6.2 s. Recorded in History." C582: the level and the reason | the same, its time as Mercury's stamp; with a reason, "Level critical (2), allowed by the reason. Why: …" (tests/test_show_commands.py `test_the_run_sends_with_the_reason_and_records_it`) | **same** |
| The summary table | Command, Answered (empty counted), Distinct answers ("5: every device's answer is its own"; "5, with Dead Time ignored"), Failed, Skipped with who | the same columns and words | **same** |
| Running (C's region 7, F's 7f) | the bar and the counts, "the summary is final when the last device is done"; F: sent, then watching Loki | the one stepper's bar and counts (`run_summary`), the same lines, re-read on `reads`, never a timer (compared by the template; the stepper's record docs/fidelity/stepper.md) | **same** |
| Filters | Find a device, Find in the answers, Compare against (Nobody first, The most common answer only when shared), Show (Only the differences off until a reference is chosen) | the same; "The most common answer is not offered: no answer is shared by two devices" under them; C's "raw answers" box is gone as C2 has nothing ignored until ticked | **same** (as C2) |
| A command's head | the command, and what is ignored, by whom and when | the same; "Grouped when the whole answer is the same; nothing is ignored." until a column is ticked; ticked, "by test-person@example.invalid at just now": a relative time after "at" | **deviation** (log: Show commands run: a time after at or by reads just now or 1 min ago (a defect, register C650 follow-up)) |
| Ignore when grouping (C580) | the header line's columns as boxes, Group again, recorded with the run | the same, the (i) beside Group again; the ignored column drawn as dots | **same** |
| Grouping again that changes nothing | "Still 5 distinct answers: each router lists its neighbours and never itself …": what ignoring can and cannot do, said | not drawn: the template has no such sentence (the shot's Dead Time did group r3 and r9, so this state was compared by the template) | **deviation** (log: Show commands run: grouping again that leaves every answer its own does not say why (a defect, register C650 follow-up)) |
| Groups | every group collapsed (C); C2 opens a chosen one and the empty answer | a group opens by itself when its command has two groups or fewer, or its answer is empty | **deviation** (log: Show commands run: a command's groups open when there are two or fewer) |
| A group's summary | a badge (neutral grey, C578) and its devices, then what the answer says ("synchronised to 192.0.2.10, stratum 2", "5 neighbours on GigabitEthernet2") | the same neutral badge and devices, then the answer's line count | **later** C2's structured parsers (each command's summary and volatile fields, "come later, measured") |
| A group's answer and actions | the answer; Compare r1 with (a select), Side by side, Open r1 (C2) | the answer; each device a chip opening its Ask tab with this run; Compare r3 with (a select) and Side by side | **same** |
| An empty answer (C579) | "No output (empty answer). r6 answered, and its answer was empty …", apart from a failure | the same words | **same** |
| Failed and skipped | red "failed" with why; amber "skipped" with who holds the device and since when | the same: "TimeoutError: did not answer in 120 s"; "r9 is being deployed to by operator@example.com, started …" | **same** |
| An answer cut at the cap | its own card (region 9), "cut at 64 kB", Close, and how to narrow it | in its group: "cut at the cap" and "N bytes, longer than one answer's cap: this is its start, never the whole" (the network's cap, 32 KiB here) | **deviation** (log: Show commands run: an answer cut at the cap is said in its group) |
| Side by side (D) | Left and Right selects, Close; each side's lines the other lacks marked | "r3 and r9, side by side: show ip interface", the two answers with the lines only one has marked; the pair is chosen on a group, and there is no Close | **deviation** (log: Show commands run: side by side has no Close (a defect, register C650 follow-up)) |
| Only the differences (C2 8t, D 11) | against your choice, "differs from r1: 2 lines only r1 has, 2 only r3 has", + and − lines, ignored columns as dots | against your choice, + and − lines; the summary names the reference ("against r3, your choice") without the line counts, which the grouped view's summary carries | **deviation** (log: Show commands run: Only the differences names the reference without the line counts) |
| F: the result's head | "Logging path on 5 devices", done in green; Test again, How does this work? | "Logging path on 2 devices", done in green, Test again (capture 07); done is green only when every line arrived, grey otherwise; the link reads "How does logging-path work?", the slug in place of words (capture 07; C901) | **deviation** (log: Show commands run: the How link reads How does logging-path work? (C901)) |
| F: the outcome counts and groups | not received (red), not sent (amber), received (green), what to act on first; received collapsed with its table | the same, the wait named; on the host "2 received", the group "received r1, s1 · after 0.4 to 1.2 s" with Device, Sent, Received by Loki, After, and the clocks' note (capture 07) | **same** |
| F: a line not received | sent at 16:20:04, no line by 16:20:34; the path broken after the device; its last line in Loki; Open s2's Logs, Test s2 again | the same parts; first, what the device's own logging trap forwards (C587); the two times drawn as Mercury's relative stamp, "sent at 1 min ago; no line in Loki by 1 min ago" | **deviation** (log: Show commands run: the logging-path result says the device's own filter first) |
| F: unknown (8g) | "Loki could not be asked", neither green nor red, nothing says the path is broken | the same words (compared by the template; tests/test_logging_path.py) | **same** |
| History's row (D 12, F) | a Reads row with what to act on | History's Show commands source (`history_sources.show_commands`; the walk's row "Logging path on 2 devices", the operator's W1 capture 08), History's own screen | **same** |
| Phone: a fleet result (E) | per command one line, "9 devices · 7 answered · 2 distinct · 1 failed · 1 skipped", the groups under it | the desk's summary table, its cells wrapping; the filters stacked, the Show select running past the card's right edge (shot `show-commands-run-page-390`, the page held to a 390 px column) | **deviation** (log: Show commands run: at phone width the Show select leaves the card (a defect, register C650 follow-up)) |
| Phone: C2 and F (G) | C2's boxes wrapping, each answer scrolling in its box, the empty answer; F's groups and Test again | the same, the answers scrolling in their boxes (tests/test_show_commands.py `test_boards_c2_and_f_in_a_real_browser_stay_inside_their_cards`) | **same** |
