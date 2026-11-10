# Fidelity: SDN › Switches (2026-11-10)

Board: `docs/boards/lab9-sdn.html` artboard A (1440), revised and self-signed under the Phase 7
mode 2026-11-10 (docs/STANDING_APPROVAL_LOG.md, "Board lab9-sdn A (SDN › Switches, Lab 9 Obj 2)
revised"). Its yellow dashed notes are the board's annotations, not page text.

**Compared from the templates and their rendering, not from shots.** tests/test_board_shots.py
has no case for this tab yet, so the regions below were read from the built templates and the
HTML tests/test_sdn_switches_v2.py's lab renders (the lab's NSOT export committed, the controller
listing one Arista, OVS's datapath 3 and one datapath no switch carries, a verified and a
rolled-back configuration recorded) and tests/v2_context.py's `_sdn_switches` provider (every
card), beside the board's HTML. A shot at 1440, 1280 and 390 is the next step of this record
(the register row the main thread names for it).

Templates compared: templates/v2/sdn_switches.html, templates/v2/_sdn_switches.html, templates/v2/_sdn_tabs.html, templates/v2/_sdn_of_config.html, templates/v2/_sdn_of_template.html, templates/v2/_sdn_of_verify.html, templates/v2/_sdn_of_slot.html
Templates sha256: `bd1cfd4634b39f267e134881ae3e778ada901e4211b79738268711442b42d32b`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Page head | "SDN (i)" | "SDN · Switches (i)" and the tab's sub-line, as every SDN tab is built | **deviation** (log: Board lab9-sdn A built, 9) |
| Tabs | Controllers, Switches (on), Flows, Apps, Protected, Policies, Responses | Controllers, Switches (on), Flows, Apps, Responses, one nav for every SDN tab (`_sdn_tabs.html`) | **later** (Protected and Policies are artboards of their own, not built) |
| Summary | five counts: marked, connected as intended, configured not connected, differs, seen by the controller not in NetBox | the five, toned as drawn, and "not configured" between differs and seen; the export's short hash after | **deviation** (log: Board lab9-sdn A built, 1) |
| Search and filters | search "name, DPID or address", Every state, Every platform | the same three, the state list the four states, the platform list each template's family; a Search button for a page with no script | **same** |
| Configure from NetBox… and Verify now | both, then "read 14:02 UTC, 40 s ago" | both, each busy on itself with its (i); the reader's last read as a stamp that ages | **same** |
| The table's columns | Switch, Platform, NetBox and intent, Controller sees, Switch reports, State, an action | Choose, Switch (with its address), Platform, NetBox and intent (controller:port · version · transport), Controller sees (DPID on the controller, or not in the list), Last configured, State, an action | **deviation** (log: Board lab9-sdn A built, 2) |
| Groups by state | "Differs from intent (1)", "Configured, not connected (1)", "Connected as intended (3)" | the same, worst first, with "Not configured (n)" | **same** |
| A switch's detail | ▾ on the row, a full-width row: NetBox, Intent, Last configured, Why not connected | the switch's name opens it in its cell: NetBox (instance, ports, defaults, what is left out), Driver, Last configured (its record on History), its verify | **deviation** (log: Board lab9-sdn A built, 3) |
| Row actions and the fold | Preview the fix… on a differing row, Verify now on a not-connected row, "show 2" | Preview the fix… on differing and not-configured rows, Verify now on a not-connected row, a checkbox per row, "and N more" past 25 | **deviation** (log: Board lab9-sdn A built, 4) |
| IPv6 | not drawn | "Arista EOS and ArubaOS-Switch take an IPv4 controller only…" under the bar | **deviation** (log: Board lab9-sdn A built, 8) |
| The templates card | ovs, arista_eos, aruba_os_switch confirmed; hp_comware draft with Confirm against a capture… disabled and why | every template that renders, its switches, its status (confirmed by, when, against which capture; or draft and why), the capture picker and Confirm against a capture… in its row, or disabled saying what to read first; "How does this work?" in the head | **deviation** (log: Board lab9-sdn A built, 7) |
| Confirm a template | the capture's select, the template's cited lines beside the capture's sections, the sentence, Confirm <template>, Cancel | the capture named with its hash, the template's lines each with why and its citations beside the capture's whole masked answer, the same sentence, Confirm <template> (busy on itself), Cancel | **deviation** (log: Board lab9-sdn A built, 7) |
| The preview card | "Configure OpenFlow on 2 switches", the export's short hash, each switch's program, Verify, Undo, Hash, Configure 2 switches, Cancel, How does this work? | the same parts; each program in its template's own forms, its release, what differs, defaults, what is left out, its own hash; Not sent with why; Verify's 12 s; the undo folded | **deviation** (log: Board lab9-sdn A built, 5) |
| The result card | "Configured 1 of 2" partial, Switch, Sent, Verify, Outcome; "one commit, two receipts"; Open the record, Back to Switches | the same table and controls; "one record per switch" and that nothing was saved; a rollback's words beside its outcome | **deviation** (log: Board lab9-sdn A built, 6) |
| The callouts | yellow dashed notes | not page text | **same** |
