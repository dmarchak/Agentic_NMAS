# Fidelity: SDN › Controllers, Flows and Responses (2026-10-27)

**Compared again 2026-10-27 ~09:5x UTC (PHASE8_PLAN 17.1 S8 to S10, S16):** the Responses tab
beside `SdnResponses.dc.html` (1440, 1280 and 390, from the same test's `sdn-responses` shots: one
scan awaiting a person, a loop log line), and Flows again with Add flow…, Edit… and Remove…
(SdnFlowEdit's controls on SdnFlows' rows). The operation card (`_sdn_op.html`, board
SdnResponse) and the flow editor (`_sdn_flow_form.html`, board SdnFlowEdit) are drawn by a
click in place, which the board-shot harness does not shoot (it shoots pages): their regions are
**later**, compared when a click-driven shot exists; their behaviour is held by
tests/test_sdn_ops_v2.py and the v2 walk's provider (tests/v2_context.py `_sdn_operations`).

Boards: `SdnControllers.dc.html` (1440), `SdnFlows.dc.html` (1440) and `SdnPhone.dc.html` (390),
PHASE8_PLAN 17.5 boards 1, 2 and 7, drawn in the agent's copy of the mockups canvas's project
folder and signed off under the Phase 7 mode 2026-10-27 (docs/STANDING_APPROVAL_LOG.md, "SDN
boards S1 to S7"). Their grey notes are notes for the builder, not page text.

Shots: `tests/test_board_shots.py::test_sdn` (`sdn-controllers` and `sdn-flows` at 1440, 1280
and 390 beside their boards; `sdn-phone` at 390 beside SdnPhone; `sdn-responses` at 1440, 1280
and 390 beside SdnResponses, `sdn-responses-suspended` at 1440 and 390 with no board, C2009; `sdn-responses-held` at 1440
and 390 with no board, C2001; `sdn-responses-stale` at 1440 and 390 and `sdn-responses-stale-held`
at 1440 beside SdnResponses' states section, C2003). The data is tests/test_sdn_v2.py's
lab: Default's `lab-controller` answered by Ryu 4.34's captured answers through the real Ryu
driver (one switch, `s1`, its nine captured flows, one meter), its flow intent recorded as a
response would record it (the meter flow, cookie ...0002, recorded; the drop flow in Mercury's
range, ...0001, not; an IPv6 drop, ...0003, recorded and not installed, its hard timeout past),
and `branch-controller` at another address refusing every connection, read twice by the SDN
reader 12 minutes apart. The board's four switches, 61 flows and ONOS second controller are
board data; the capture has one switch, and an ONOS connection cannot be saved (its driver is
not built), so the second controller is a Ryu one that does not answer.
Templates compared: templates/v2/sdn.html, templates/v2/_sdn_view.html, templates/v2/_sdn_answer.html, templates/v2/_sdn_responses.html, templates/v2/_sdn_op.html, templates/v2/_sdn_flow_form.html, templates/v2/_sdn_log.html
Templates sha256: `cc7ac50ca45c15bdd0cdea1f93c5bbf85187515a8f4f9bb87279b5fa300c1072`

**Compared again 2026-10-28 ~15:0x UTC for C2082** (the every-carried-field check sees the SDN
payload, `g`): one template line changed, `_sdn_responses.html`'s Allowed risk select, whose
options are now drawn from the view's `risks` (`modes.RISKS`, carried and drawn nowhere) instead
of written out; for low and medium the select renders byte for byte as before (checked by
rendering both), so no pixel moves. The payload trims (the stored read without its raw `value`,
the mode as `mode` and `words`, no `remove_why`, no expired count) change no drawing. Every
`test_sdn` shot taken twice, this change and the commit before it (8e01c4b6, through
scripts/nmas-control), and the page shots compared pixel by pixel: the only differences are the
run's own data (the log's and the stamps' times, "read 1 min ago" against "just now", a
response's cookie, wrapping one line in `sdn-responses-held`), and the top bar's AI chip caught
reading or read. No region's verdict changes.

**Compared again 2026-10-28 ~14:1x UTC for C2077** (a lost response a newer response already
answers: `_sdn_view.html` draws it **Answered**, naming the newer response, with no
Re-apply…): `SdnFlows.dc.html` revised in the agent's copy of the project folder (s2 draws a
Not in force line with Re-apply… and an Answered line, the newer response's flow installed and
the lost ones missing in its table, and a builder's note; signed off under the Phase 7 mode,
docs/STANDING_APPROVAL_LOG.md "SDN C2077"), and a new shot beside it, `sdn-flows-answered`
(1440, 1280 and 390): the lab above with the `sdn-flows-lost` data, then the awaiting scan
confirmed by a person as a newer drop of 192.0.2.1, recorded 30 s before the read for 600 s and
in the capture's table, read again. The shot refuses to run unless the page draws the answered
line and no Re-apply… form (its data once drew Not in force: the shot's lost record named no
rule, so nothing could cover it; both records now carry the scan rule, as every response's
does). At 1440 the Answered line sits under Add flow… where the board draws it, the newer
response's id with its operation beside it in faint, its action and source, its clock time in
UTC, "Nothing to re-apply." and the (i); at 390 it wraps above the table. The `sdn-flows-lost`
shots were taken again: unchanged (Not in force with Re-apply…). The page's Needs attention count
fell from 17 to 16 between the two (the lost response's row resolved, C2070; the confirmed scan
no longer awaits). The board draws both lines on s2 of four switches; the capture has one switch
and one lost response, so each state is shot on its own (`sdn-flows-lost`, `sdn-flows-answered`).

**Compared again 2026-10-28 ~09:3x UTC for C2003** (never a frozen page shown as current:
`_sdn_view.html` draws a hidden note under the tabs on every tab, which static/js/nmas_v2.js
`staleNote` shows past the region's promise, the SDN reader's page promise of 90 s, or while the
live channel is down): `SdnResponses.dc.html` revised with a states section drawing the note's
three states (signed off under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md "SDN C2003"), and
two new shots beside it, `sdn-responses-stale` (1440 and 390: past the promise, nothing open)
and `sdn-responses-stale-held` (1440: a preview open, a redraw held, then past the promise).
Each shot sets the note's stale moment in the past instead of waiting 90 s, so its "Last
updated" reads "just now" where the board reads "2 min ago". The `sdn-responses` shots are
otherwise unchanged (the note is hidden while the page is current); the board's states section
sits below its rules card as a section of states, not a place on the page: the page draws the
note where the section's note says, between the tabs and the summary.

**Compared again 2026-10-28 ~04:0x UTC, the three changes below merged** (C2001's hold and
C2018's re-apply each changed `_sdn_op.html`, compared apart in their own trees): the SDN shots
taken again from the merged tree (`tests/test_board_shots.py -k test_sdn`, 1 passed), and
`sdn-responses-held` (1440) and `sdn-flows-lost` (1440) read: the hold's note with Show it now
above the open preview, the Mode card's stage line and Turn AUTO on drawn disabled with its
reason, and the Not in force line with Re-apply… above s1's flow table, each as its region
below says; nothing else moved.

**Compared again 2026-10-28 ~03:1x UTC for C2001** (an announcement never takes an open card
away: `_sdn_op.html` and `_sdn_flow_form.html` carry `data-holds-live`, which static/js/nmas_v2.js
reads to hold the region's live redraw): a new shot, `sdn-responses-held` (1440 and 390, no
board), the scan's preview opened in place and the SDN announcement dispatched, the redraw held.
The markup otherwise draws nothing new (the attribute is not drawn), so the `sdn-responses` shots
are unchanged; the hold's note is one region, below, a deviation. The operation card itself
stays **later** against SdnResponse (this shot is the first click-driven one, and is not a
region-by-region comparison with that board).

**Compared again 2026-10-28 ~02:5x UTC for C2009** (AUTO only on a network marked lab,
PHASE8_PLAN 17.7's guard; `_sdn_responses.html`'s Mode card): the `sdn-responses` shots again
(1440, 1280 and 390, beside `SdnResponses.dc.html`), Default not marked, and a new shot,
`sdn-responses-suspended` (1440 and 390, no board: AUTO turned on while Default was marked lab,
then Default marked production). The three regions below are what changed; SdnResponses draws
no stage, so each is a deviation. The rest of the Mode card is as its row says.

**Compared again 2026-10-28 ~03:3x UTC for C2018** (a lost response: `_sdn_view.html`'s Not in
force line with Re-apply… on its switch, and `_sdn_op.html`'s re-apply card): Flows shot again
beside `SdnFlows.dc.html` at 1440, 1280 and 390 from the same test's new `sdn-flows-lost` shots.
The data is the lab above, plus a drop of 192.0.2.1 recorded two minutes before the read for 600
s and absent from the captured table, as after a switch restart, read again by the SDN reader.
The `sdn-flows` shots without it were compared too: unchanged, with no line drawn when nothing
is lost. The page's Needs attention count rose by the response's row (16 to 17 in the header).
The re-apply card is drawn by a click, as the other operation cards are: **later**, held by
tests/test_sdn_reapply.py and the v2 walk's provider (tests/v2_context.py `_sdn_reapply`).

**Hashed again 2026-10-27 for PHASE8_PLAN 17.1 S7** (the AI's classification and Classify on an
awaiting response, `_sdn_responses.html`): the two regions below compared by reading the
template against SdnResponses' region list, with no new shot; the classification's region is
**later** until a shot plants one, and Classify is a deviation.

**Hashed again 2026-10-27 for C1968** (the Lab 8 walk's step 10: a response stays awaiting a
person when its threat stops, and a refused classification is said with its call): the two
regions below compared by reading `_sdn_responses.html`'s awaiting card against SdnResponses'
region list, with no new shot; both are additions the board does not draw, each a deviation.

**Compared again 2026-10-27 ~18:0x UTC for C1971** (the loop's log, `_sdn_log.html`, added to
the templates compared, and its include in `_sdn_responses.html`): the loop's region read
against SdnResponses' log, with no new shot; its scroll, Run and Download log are a deviation.

**Hashed again 2026-10-27 ~19:1x UTC for the Lab 8 walk's objective 3.1** (the response policy:
each rule's allowed responses drawn in the rules table and set under it; a response proposed
with no action when the policy could not be read; `_sdn_responses.html`): the two regions below
compared by reading the template against SdnResponses' region list, with no new shot; both are
additions the board does not draw, each a deviation. The loop's log region is unchanged here
(its lines' words changed, not its markup).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | SDN under OBSERVE, between Topology and Logs | SDN between Topology and Show commands (Show commands, absent on the board, stays before Logs), with its icon | **same** |
| Heading and line | "SDN · Controllers" / "SDN · Flows" and the board's line | the same words, with the page's (i) to the manual's SDN page | **same** |
| Tabs | Controllers, Flows, Responses, each a link | Controllers, Flows and Responses, each a link (S8 to S10 built) | **same** |
| Controllers' summary | "2 controllers · 1 connected · 1 not answering · 4 switches · read 18 s ago" | the same shape, counted from the read ("1 switch"); the age on hover too | **same** |
| A connected card's head | name, connected chip, Test connection, Edit connection, (i) | the same; the (i) is beside Test connection, whose manual section it opens (the rule: "How does this work?" right after its control) | **deviation** (log: SDN S11: the card's info link beside Test connection) |
| Driver, Northbound, Southbound | "Ryu (ofctl_rest) · built", the URL and "TLS not used", the southbound and "informational" | the same | **same** |
| Version | "Ryu 4.34" | "not reported (Ryu's ofctl_rest reports no version)": the driver reads none | **deviation** (log: SDN S11: Version "not reported", Ryu's REST reports none) |
| Cluster role | "standalone (this driver reports no cluster)" | "not reported (this driver reports no cluster)": nothing read says standalone | **deviation** (log: SDN S11: Cluster role "not reported", never assumed standalone) |
| Switches | N connected, each DPID a link, "discovered via this controller, not adopted" | the same; each DPID opens its flows on Flows (`?q=<dpid>`), since the switch's own device page (board 5) is a later step; past 12, "and N more, on Flows" | **deviation** (log: SDN S11: a DPID opens its flows on Flows until the switch's device page) |
| Can | the capability chips, "read topology: not offered by this driver" | the same | **same** |
| Controller's own flows | "cookie 0", the note | the same | **same** |
| Last read | "18 s ago · flows, port stats and meters of 4 switches, 0 failed" | the same shape | **same** |
| Not answering | notice: since when, what failed, reads in a row, "flows below are as last read", "a row on Needs attention until it answers"; Driver; Switches at the last good read | the same, but no Needs attention sentence: that row is a later S11 step and the page does not claim it | **later** S11's Needs attention rows (controller unreachable) |
| Empty state | "No SDN controller is connected to this network. Add one in Settings › Integrations." with the link, nothing else | the same (tests/test_sdn_v2.py `test_the_empty_state_is_the_board_s`, not shot) | **same** |
| Not read yet | not drawn | a connection saved before the reader's next run: "Not read yet. The SDN reader reads every 30 seconds"; the store never read, or its last attempt failed, said above the cards | **deviation** (log: SDN S11: "not read yet" and the reader's own failures said) |
| Flows' summary | "4 switches · 61 flows: 3 Mercury's · 57 the controller's own · 1 unauthorised · 1 of Mercury's missing · 1 meter · lab-controller, read 18 s ago" | the same shape over the capture ("1 switch · 9 flows …"), every controller named | **same** |
| Granularity note | under the summary, once, when it limits a rule | under the summary, per switch whose flows are L2 or L3 only, in closed_loop's words (shot with the capture's L2 flows alone in tests/test_sdn_v2.py, not at 1440) | **same** |
| Filter | text, "Hide the controller's own flows" ticked, Show | the same | **same** |
| Switches folded | a `<details>` per switch, the wrong ones open, chips (unauthorised, missing, as expected), counts | the same, kept open across redraws (`data-keep`) | **same** |
| A flow row | owner chip, priority, match, actions, packets, timeouts, cookie, Remove… (SdnFlowEdit: Edit… and Remove… on each flow row) | the same columns; the unauthorised row's why under its chip; Remove… on every flow and Edit… on Mercury's, each with its (i), each opening the editor in a row under the flow | **same** |
| Add flow… | SdnFlowEdit: "Add flow… sits on each switch in the list" | Add flow… with its (i) at the top of each opened switch | **same** |
| Mercury's flow | "Mercury's installed as expected", "Its response" link | the same chip and words; no response link (a flow's operation is read on History, not yet linked from its row) | **later** S11 (a flow's response linked from its row) |
| A lost response (C2018) | revised for C2077: s2's "Not in force" line, "Rate-limit the source (192.0.2.40): 1 flow (…0b) and meter 3 missing, 6 min 40 s of its hard timeout left (until 10:46 UTC)", Re-apply… and How does this work? | under Add flow…, one line per response the switch lost before its hard timeout: "Not in force", the response's action and source, what is missing (its flows' cookies, its meter), the time left and the expiry's clock time, then Re-apply… with its (i); the switch opens, as one with something wrong does; at 390 the line wraps above the table | **same** (drawn first as a deviation, log: SDN C2018; the revised board draws it) |
| A lost response answered by a newer one (C2077) | s2's "Answered" line (neutral): the lost response's action and source and what is missing, "and a newer response answers the same threat on this switch: response resp-… (operation sdnop-…), <its action and source>, in force until 10:52 UTC. Nothing to re-apply.", How does this work?; no Re-apply… | the same words and place (shot `sdn-flows-answered` at 1440, 1280 and 390): the badge muted, the operation in faint only when it differs from the response's id, the clock time with its full UTC time on hover, the lost response's operation and expiry on hover of its name; the (i) opens the re-apply section; its flows stay "Mercury's, missing" in the table with the reader's words, as the board's do | **same** |
| A record not installed | "Mercury's, missing" for one expired at its hard timeout, "nothing to do" | expired is "Mercury's, expired", neutral, not counted missing (S5's classify tells expired from missing); missing stays warn | **deviation** (log: SDN S11: an expired flow is "expired", never "missing") |
| The board's departure note | the unauthorised flow a Needs attention row | not drawn: that row is a later S11 step | **later** S11's Needs attention rows (unauthorised flows) |
| Meters | switch, meter, rate, packets in band, owner chip and "its response" | the same columns; the owner from the flows that use the meter; no response link | **same** |
| Phone width | each tab stacked: summary, cards, a flow row a block, tables scrolling in their box | the same; a controller's card keeps its whole list, stacked, where SdnPhone draws a one-line card | **deviation** (log: SDN S11: the phone's controller card keeps its fields) |
| Responses' summary | "1 awaiting approval · mode HITL · the loop running every 10 s · 3 responses in the last 24 h (2 expired …, 1 in force)" | "1 awaiting approval · mode HITL · the loop stopped": no count of the day's responses (they are read on History) | **deviation** (log: SDN S8: Responses' summary without the day's count) |
| An awaiting response's head | "Port scan from <source> on <dpid>", the confidence chip, "Detected 40 s ago by the scan rule: …", "Open the alert" | the detection's title, source and switch, the confidence chip, "Detected <age>: <the rule's words> · an alert with its evidence pack"; no "Open the alert" link | **deviation** (log: SDN S8: an awaiting response without its alert link) |
| The AI's classification | an AI-marked box: threat, severity, model and cost, evidence ids, the recommendation | when a classification is kept (S7, 2026-10-27): a box marked AI with the threat or "No threat", its kind and severity, by whom (the loop or a person) and when, the model and cost (the call's id on hover), the reasoning, the recommendation with its catalogue action, the devices named and the evidence ids cited; with none, one line naming who chose the action (the catalogue's default, chosen in code, and why no AI classification was made). Compared by reading the template against the board's list, not yet shot: the harness's `sdn-responses` shot plants no classification | **later** a shot with a kept classification (tests/test_board_shots.py) |
| Its actions | Preview the drop…, Choose another action…, Dismiss with a reason…, How does this work? | "for N s" (the response's hard timeout, editable), Preview the <action>…, a reason field and "Dismiss with this reason", each with its (i); no Choose another action… | **deviation** (log: SDN S8: the awaiting card's actions) |
| A response whose threat stopped (C1968) | not drawn: the board's response awaits while its threat runs | "Inactive" and "Threat no longer active since <time>: the detection resolved, and this response still awaits your approval or dismissal", under the detection's line; the card otherwise unchanged, its classification kept | **deviation** (log: SDN C1968: a response stays awaiting when its threat stops) |
| A refused classification (C1968) | not drawn | the card's classification line says "AI classification refused: <why>; proposed by the catalogue default, <action> (AI call <id>)" and links "The refused answer in History" (the call) | **deviation** (log: SDN C1968: a refused classification said, its call linked) |
| Classify | not drawn: the board's box is filled by the loop | **Classify** (AI-marked, its hover the task, model and cap; disabled with the reason while AI cannot answer), and "Classify again" once a classification is kept, before Preview, with its (i) | **deviation** (log: SDN S7: a person's Classify on an awaiting response) |
| Mode | HITL and AUTO as radio rows, Reason, Until (a date), Allowed risk, Turn AUTO on… | the mode chip and its words; Reason, For (hours, at most 24), Allowed risk, Turn AUTO on; while on, who, why and until when, and Turn AUTO off | **deviation** (log: SDN S9: AUTO for N hours, not until a date) |
| Mode: the network's stage (C2009) | not drawn: the board's Mode card has no stage | one line under the mode's words: "This network is marked lab.", or "This network is not marked" (or "is marked pilot", "is marked production", or why its stage cannot be read); "AUTO is turned on only on a network marked lab until the AUTO production-readiness gate is complete" with a link to the stage on Settings › Integrations › SDN controllers (shot at 1440, 1280 and 390: not marked; at 1440 and 390: marked production) | **deviation** (log: SDN C2009: the Mode card says the network's stage) |
| Mode: Turn AUTO on off lab (C2009) | "Turn AUTO on…", pressable | on a network not marked lab, drawn disabled with its reason on the control, "Turn AUTO on (Not available: this network is not marked lab)", the server refusing it anyway, naming the stage and the gate; at 390 the button's words and its reason wrap side by side inside the card (shot at 1440, 1280 and 390) | **deviation** (log: SDN C2009: Turn AUTO on drawn disabled on a network not marked lab) |
| Mode: AUTO suspended (C2009) | not drawn | AUTO recorded on while the network is not marked lab: the AUTO chip and its words, the stage line, an amber notice "AUTO is suspended: it is recorded on, and nothing runs unattended while this network is not marked lab; each response awaits a person. Turn AUTO off, or mark the network lab.", and Turn AUTO off (shot `sdn-responses-suspended` at 1440 and 390) | **deviation** (log: SDN C2009: AUTO drawn suspended on a network marked otherwise) |
| A refresh held while a card is open (C2001) | not drawn: the board does not say what a refresh does to an open preview | while a preview, its result or refusal, or the flow editor is open in place, an announcement's redraw of the region is held; the card says at its top "Paused while you review this: newer data is waiting." with **Show it now** (busy on itself, "Showing…"; it closes the card and redraws, sending nothing); a typed reason holds as every page's field does (C459). Shot `sdn-responses-held` at 1440 and 390 | **deviation** (log: SDN C2001: a refresh held while an operation card is open) |
| Not current (C2003) | the states section: between the tabs and the summary, an amber notice "Last updated 2 min ago: no update has arrived in the 90 s it promises, so this page may be out of date." with Reload; "live updates stopped" in place of the cause while the channel is down; with a card open, no Reload and "a reload would close the card open below. Send or close it first.", or "newer data is waiting, held for the card open below" when a redraw was held; nothing while current | the same words and places on every SDN tab (shot on Responses: `sdn-responses-stale` at 1440 and 390, Reload wrapping under the words at 390; `sdn-responses-stale-held` at 1440, the note above the summary and the card's own "Paused while you review this" note kept); Reload a link to the tab's own page, Flows' filter kept | **same** |
| The loop | its state chip, "every 10 s · detect, classify, respond", Stop, the log | the same; stopped, "every N s" and Start | **same** |
| The loop's log | the latest lines, newest first, each line's time, step and words | one run whole (from its start line), newest first, in a box that scrolls; above it **Run** (each run by its job id, start time in UTC and line count) and **Download log** (the run as text); a line naming the lines drawn of the run's and its first and last times; past 2,000 lines the newest 2,000, said (C1971) | **deviation** (log: SDN C1971: the loop's log scrolls over the whole run, with Run and Download log) |
| Detection rules | the table with each threshold editable, Save thresholds…, the timeout line | the same table read-only, and the timeout line with the ceiling; no Save thresholds… | **later** S8's thresholds edited on this tab (until then written by `list_settings.write`) |
| Response policy (objective 3.1) | not drawn: the board's response takes the catalogue's action for its rule | a "Responses allowed" column in the rules table (each rule's allowed actions, its default marked), and under it **Response policy**: where it comes from, per rule a default select and a tick per other action that answers the rule, **Save the response policy** with its (i), refusals said beside it; a red notice when the policy cannot be read | **deviation** (log: SDN 3.1: each rule's allowed responses on the rules card) |
| A response with no action proposed (objective 3.1) | not drawn | "No action is proposed: the network's response policy could not be read when this was detected", in place of the Proposed line | **deviation** (log: SDN 3.1: a response proposed with no action when the policy is unreadable) |
| Needs attention | "a row on Needs attention until it is confirmed, dismissed …" | not said: that row is a later S11 step | **later** S11's Needs attention rows (a response awaiting approval) |
| The response's preview and result (SdnResponse) | the card in place: what it does, exactly these requests, what will not happen, Verify, checks, bound hash, Send N requests | drawn in place by a click: what it does, the detection and its checked parameters, exactly these requests, what will not happen, the warnings, Verify (its limit said), the bound hash, Send N requests; the result: outcome, what was sent, Verify, counters, rollback, the record | **later** a click-driven shot (the harness shoots pages) |
| The flow editor (SdnFlowEdit) | the form, the prerequisite refusal, the preview, Edit's and Remove's words, Explain this flow table (AI) | the form, the refusal naming the field, the preview card; Edit's and Remove's words; no Explain (S19, after cost safety) | **later** a click-driven shot; Explain is S19 |
| Responses at phone width | stacked | the card's fields and buttons wrap inside it (390 shot) | **same** |
