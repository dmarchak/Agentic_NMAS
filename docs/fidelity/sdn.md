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
and 390 beside their boards; `sdn-phone` at 390 beside SdnPhone). The data is tests/test_sdn_v2.py's
lab: Default's `lab-controller` answered by Ryu 4.34's captured answers through the real Ryu
driver (one switch, `s1`, its nine captured flows, one meter), its flow intent recorded as a
response would record it (the meter flow, cookie ...0002, recorded; the drop flow in Mercury's
range, ...0001, not; an IPv6 drop, ...0003, recorded and not installed, its hard timeout past),
and `branch-controller` at another address refusing every connection, read twice by the SDN
reader 12 minutes apart. The board's four switches, 61 flows and ONOS second controller are
board data; the capture has one switch, and an ONOS connection cannot be saved (its driver is
not built), so the second controller is a Ryu one that does not answer.
Templates compared: templates/v2/sdn.html, templates/v2/_sdn_view.html, templates/v2/_sdn_answer.html, templates/v2/_sdn_responses.html, templates/v2/_sdn_op.html, templates/v2/_sdn_flow_form.html
Templates sha256: `949a0a6ccf1a32af972c938906217437b4a54995f536d69f79a679c901659af6`

**Hashed again 2026-10-27 for PHASE8_PLAN 17.1 S7** (the AI's classification and Classify on an
awaiting response, `_sdn_responses.html`): the two regions below compared by reading the
template against SdnResponses' region list, with no new shot; the classification's region is
**later** until a shot plants one, and Classify is a deviation.

**Hashed again 2026-10-27 for C1968** (the Lab 8 walk's step 10: a response stays awaiting a
person when its threat stops, and a refused classification is said with its call): the two
regions below compared by reading `_sdn_responses.html`'s awaiting card against SdnResponses'
region list, with no new shot; both are additions the board does not draw, each a deviation.

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
| The loop | its state chip, "every 10 s · detect, classify, respond", Stop, the log | the same; stopped, "every N s" and Start; the log newest first, each line's time, step and words | **same** |
| Detection rules | the table with each threshold editable, Save thresholds…, the timeout line | the same table read-only, and the timeout line with the ceiling; no Save thresholds… | **later** S8's thresholds edited on this tab (until then written by `list_settings.write`) |
| Needs attention | "a row on Needs attention until it is confirmed, dismissed …" | not said: that row is a later S11 step | **later** S11's Needs attention rows (a response awaiting approval) |
| The response's preview and result (SdnResponse) | the card in place: what it does, exactly these requests, what will not happen, Verify, checks, bound hash, Send N requests | drawn in place by a click: what it does, the detection and its checked parameters, exactly these requests, what will not happen, the warnings, Verify (its limit said), the bound hash, Send N requests; the result: outcome, what was sent, Verify, counters, rollback, the record | **later** a click-driven shot (the harness shoots pages) |
| The flow editor (SdnFlowEdit) | the form, the prerequisite refusal, the preview, Edit's and Remove's words, Explain this flow table (AI) | the form, the refusal naming the field, the preview card; Edit's and Remove's words; no Explain (S19, after cost safety) | **later** a click-driven shot; Explain is S19 |
| Responses at phone width | stacked | the card's fields and buttons wrap inside it (390 shot) | **same** |
