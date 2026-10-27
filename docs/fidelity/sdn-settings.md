# Fidelity: Settings › Integrations, the SDN controllers card (2026-10-27)

Board: `SdnSettings.dc.html` (1440), PHASE8_PLAN 17.5 board 6, drawn in the agent's copy of the
mockups canvas's project folder and signed off under the Phase 7 mode 2026-10-27
(docs/STANDING_APPROVAL_LOG.md, "SDN boards S1 to S7"). Its grey note is a note for the builder.

Shots: `tests/test_board_shots.py::test_sdn` (`sdn-settings` at 1440, 1280 and 390, the card at
the foot of Default's Integrations tab; `sdn-settings-edit` at 1440 and 390, the card with Edit
pressed on `lab-controller`), on tests/test_sdn_v2.py's lab with its two connections (one
answering Ryu's captured answers, one refusing). Test connection's answer, a refused Save and
Remove… are compared by the template and tests/test_sdn_v2.py's `TestTheSettingsCard`, not shot.
Templates compared: templates/v2/_sdn_settings.html, templates/v2/_sdn_answer.html
Templates sha256: `b2dd1f6e797342763f5d1cf54aac5506ffdcd7b3ac9092bfa6c3d20c328db79c`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is | "Settings · Integrations", tabs Installation, Integrations, Networks, the card alone | the network's Settings page ("Settings · Default", the scope bar, its Integrations and Network tabs), the card at the foot of Integrations below the group cards, spanning the tab | **deviation** (log: SDN S11: the SDN card on a network's Integrations tab, as Settings is built) |
| Card head | "SDN controllers · network Default", "How does this work?" | the same | **same** |
| A saved connection | name, state chip, "Ryu (ofctl_rest) · URL · no credential · TLS not used", Test connection, Edit, Remove… | the same, the state the SDN reader's last read (connected, not answering, not read yet); each control with its (i) | **same** |
| Test connection on a row | answers in place | the answer under the row's words (Answered: N switches; Couldn't connect: why) | **same** |
| Edit | opens the form with the connection's values | the form "Edit <name>", its values drawn, the name kept (read-only, said why), a credential never drawn ("set: type to replace"), Cancel | **same** |
| Remove… | not drawn past the button | in place of the row: what removing does, what survives (the flow-intent records), Remove <name> and Cancel | **same** |
| The form's fields | Name, Driver, Northbound URL, Username, Password, Verify TLS, Southbound address, own cookies, four to a row, labels above, hints under | the same fields, order, hints and layout; two to a row below 1100 px, one at phone width | **same** |
| Driver list | Ryu selectable; ONOS, OpenDaylight, ACI, NSX, Apstra, CloudVision (later) and Floodlight (unmaintained) disabled | the same, from the drivers' declarations: ONOS "(later: not built yet)" where the board wrote "(later: read-first, not built yet)", ONOS being a later read-write driver | **deviation** (log: SDN S11: ONOS's status from its declaration, later and not read-first) |
| Credentials | typed to set, never shown, a blank keeps the stored one | the same; "set: type to replace" when one is stored | **same** |
| Test connection and Save | Test connection, Save | the same, each busy on itself with its (i) | **same** |
| Test's answer | "Answered: Ryu 4.34, 4 switches" or "Couldn't connect: <the reason>" | "Answered for <URL>: N switches connected; version not reported (Ryu's ofctl_rest reports no version)" or "Couldn't connect to <URL>: <the reason>", naming the URL the answer is for | **deviation** (log: SDN S11: Test's answer names its URL and says no version is reported) |
| Save refused until Test answered | the rule, in words | refused in place beside Save, naming the URL ("Test connection has not answered for <URL> as typed"); a Test for another URL, driver or TLS choice, or one older than 30 minutes, refused by name | **same** |
| The note under the form | the board's sentence | the same sentence | **same** |
