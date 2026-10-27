# Fidelity: SDN › Controllers and SDN › Flows (2026-10-27)

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
Templates compared: templates/v2/sdn.html, templates/v2/_sdn_view.html, templates/v2/_sdn_answer.html
Templates sha256: `eba1923dd3b05731df0998af2f76c75b8cf4f94ee01ebda859565406057e038e`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | SDN under OBSERVE, between Topology and Logs | SDN between Topology and Show commands (Show commands, absent on the board, stays before Logs), with its icon | **same** |
| Heading and line | "SDN · Controllers" / "SDN · Flows" and the board's line | the same words, with the page's (i) to the manual's SDN page | **same** |
| Tabs | Controllers, Flows, Responses, each a link | Controllers and Flows links; Responses drawn not yet open, its reason on hover | **deviation** (log: SDN S11: Responses drawn as a tab not yet open, until S8 to S10) |
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
| A flow row | owner chip, priority, match, actions, packets, timeouts, cookie, Remove… | the same columns; the unauthorised row's why under its chip; Remove… drawn disabled with its reason, "removing a flow is built with Responses, S8" | **deviation** (log: SDN S11: an unauthorised flow's Remove… disabled until S8, its why drawn) |
| Mercury's flow | "Mercury's installed as expected", "Its response" link | the same chip and words; no response link (Responses are S8) | **later** S8 (a flow's response) |
| A record not installed | "Mercury's, missing" for one expired at its hard timeout, "nothing to do" | expired is "Mercury's, expired", neutral, not counted missing (S5's classify tells expired from missing); missing stays warn | **deviation** (log: SDN S11: an expired flow is "expired", never "missing") |
| The board's departure note | the unauthorised flow a Needs attention row | not drawn: that row is a later S11 step | **later** S11's Needs attention rows (unauthorised flows) |
| Meters | switch, meter, rate, packets in band, owner chip and "its response" | the same columns; the owner from the flows that use the meter; no response link | **same** |
| Phone width | each tab stacked: summary, cards, a flow row a block, tables scrolling in their box | the same; a controller's card keeps its whole list, stacked, where SdnPhone draws a one-line card | **deviation** (log: SDN S11: the phone's controller card keeps its fields) |
