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

Templates compared: templates/v2/sdn_switches.html, templates/v2/_sdn_switches.html, templates/v2/_sdn_tabs.html, templates/v2/_sdn_of_config.html, templates/v2/_sdn_of_template.html, templates/v2/_sdn_of_verify.html, templates/v2/_sdn_of_slot.html, templates/v2/_sdn_built_from.html
Templates sha256: `b9770db2dc70c3145152fee00463f7a4e80d12096ab05b16315451ebf8e52bc0`
Hashed again 2026-11-11 for C2996 and C2779 (the operator, 2026-11-10: "arista_eos renders ALL
bound ports in ONE 'bind interface' line ... plus a read-back of the bound set (C2779)"). One
region moved, in `_sdn_of_config.html`: **the preview card's Verify line** ends with what
Verify checks on that switch's family beyond the two checks it always named, each from the
plan (`verify_also`); for an Arista, "; the switch's own show openflow lists the program's
bound interfaces". An Open vSwitch or ArubaOS-Switch plan carries none, and its line reads as
it did. The result card is unmoved: an Arista's Verify now counts three checks where it counted
two, and its program one `bind interface` line where it held one per port (11 lines for the
lab's blank Arista, where the paragraph below says 12). Compared by reading the template and
the HTML tests/test_sdn_switches_v2.py's lab renders
(`test_an_aristas_preview_holds_one_bind_line_and_names_the_read_back`); no new shots were
taken, and no approval-log line is claimed: the words follow the operator's decision, and the
board's revision is the operator's to ask for (the templates before hashed
`af9ed77a948772cfbc22345db884f7a9d1f5595869c51e787235979697e4cc33`).

Hashed again 2026-11-11 for the operator's sitting on the lab's hardware (2026-11-10: "The
configure result table shows headings and no rows. It must list each switch: what was sent,
before -> after per value, Verify's time, outcome; 'already as intended, nothing sent' where
nothing changed", and the result card "must name its source and each value's origin"). Two
regions moved, both in `_sdn_of_config.html`, and one template joined the list
(`_sdn_built_from.html`, the source sentence the cards and History share). **The result card:**
the table is Switch, Sent, Before → after, Verify, Outcome, a table body per switch; Sent is
the line count or "1 transaction" with the lines under "What was sent", or "already as
intended, nothing sent"; Verify is how many checks passed, how long they took and when, each
check's words with the operation's id and the datapath under "Details for the record"; under
each switch a row saying what its program was built from (the NSOT export and its commit as
links, then each value with where it came from). **The preview card:** each switch's "Differs
now" line is a Changes row (each value before → after) and a Values row (the same source
sentence); a switch already as intended says so in one sentence that holds for Open vSwitch
too. Board A's result card draws four columns and no source: the built card is ahead of the
board by the operator's own words, so the board's revision is the operator's to ask for, and no
approval-log line is claimed here. Compared from new shots at 1280 and 1920 of
tests/test_sdn_switches_v2.py's lab (four switches: one sent 12 lines, one as intended, one
Open vSwitch transaction, one rolled back), before and after, and by reading the templates;
no other region moved (the templates before hashed
`ce67305bca404038213e1ee253f4a7e3c401472529a40d5e7016ab9c9580d738`). The large empty block the
"Paused while you review this" note stood in, and the table's inner scroll, were the
stylesheet's (`.held-note`'s flex basis in a column card), not a template's.

Hashed again 2026-11-10 for Lab 9 Objective B2 (board lab9-sdn E): `_sdn_tabs.html` gains
Policies between Apps and Responses (docs/fidelity/sdn-policies.md); the tab row is otherwise as
compared, and no other region moves (the templates before hashed
`bd1cfd4634b39f267e134881ae3e778ada901e4211b79738268711442b42d32b`).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Page head | "SDN (i)" | "SDN · Switches (i)" and the tab's sub-line, as every SDN tab is built | **deviation** (log: Board lab9-sdn A built, 9) |
| Tabs | Controllers, Switches (on), Flows, Apps, Protected, Policies, Responses | Controllers, Switches (on), Flows, Apps, Policies, Responses, one nav for every SDN tab (`_sdn_tabs.html`) | **later** (Protected is an artboard of its own, not built; Policies built 2026-11-10, docs/fidelity/sdn-policies.md) |
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
| The preview card | "Configure OpenFlow on 2 switches", the export's short hash, each switch's program, Verify, Undo, Hash, Configure 2 switches, Cancel, How does this work? | the same parts; each program in its template's own forms, each value it changes (before → after), the values it was built from with where each came from, its release, defaults, what is left out, its own hash; Not sent with why; Verify's 12 s; the undo folded | **deviation** (log: Board lab9-sdn A built, 5) |
| The result card | "Configured 1 of 2" partial, Switch, Sent, Verify, Outcome; "one commit, two receipts"; Open the record, Back to Switches | the same controls; the table Switch, Sent (or "already as intended, nothing sent"), Before → after, Verify (checks passed, how long, when), Outcome, and under each switch what it was built from; "one record per switch" and that nothing was saved; a rollback's words beside its outcome | **deviation** (log: Board lab9-sdn A built, 6) |
| The callouts | yellow dashed notes | not page text | **same** |
