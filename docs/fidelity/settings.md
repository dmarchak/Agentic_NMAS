# Fidelity: Settings, a network's page

A network's Settings page as built (`/v2/settings/network/<name>`: the scope bar, the mode's
banner, the Integrations and Network tabs with a card per group, the Inventory source and
Delete cards, the New network card from the scope bar, the deleted network's page) and the top
bar's network picker that the walks used beside it, compared region by region with their
boards (C650's step), after the operator's walks W2 (2026-10-16, steps 30 to 40: Default's
Save from two tabs, the throwaway network W2 walk created, its inventory source changed and put
back, the picker, the delete) and W3 (2026-10-17, steps 5, 8, 9, 14, 15 and 38 to 43: W2 walk's
deleted page, W3 walk created, its source previewed, a tab drawn before the delete, two
deletes). No shot test exists for this page (tests/test_board_shots.py has none), so the page
as built is the operator's captures: W2's 23 (the stale tab refused), 24 (Default's Network tab
after the undo), 26 and 27 (the Inventory source on NetBox and back), 38 and 39 (W2 walk's page
with the picker open; drawn before C1029 made a deleted network's page); W3's 01 and 02 (the
deleted page at desktop and phone width), 12 to 14 (the source's preview and the card), 41
(the delete's result), 43 and 47 (the deleted page) and 44 (a stale tab's preview refused).
Installation (`settings_installation.html`) is its own page and its own record.

Boards: on "NMAS v2 mockups", page "P.8 Settings per network" (A to E approved 2026-10-05, F to J
redrawn and approved the same day): `SettingsNetwork.dc.html` (A to E: a network's
integrations, one card per group with its origin; B and C, a group's switch previewed; D,
Default's view), `SettingsGlobal.dc.html` (H, the scope bar; F, Installation, not this page;
G, Default counting who inherits, with the warning on a Default change),
`SettingsInherit.dc.html` (I, a network's creation and its standalone page; J, the switch
previewed) and `NetworkPicker.dc.html` (N, the picker, approved 2026-10-05). The 2026-10-10
lines "Board I's create form and a delete card" and "Board: a network's Inventory source card",
and the 2026-10-17 line "Board: a deleted network's Settings page" (board
`SettingsNetworkDeleted`, not in the local copy of the canvas this record was read beside, so
compared with the line's words), drawn under the Phase 7 mode.
Shots: the operator's captures above; the boards `SettingsNetwork`, `SettingsGlobal`,
`SettingsInherit` and `NetworkPicker` at 1440, rendered in the same headless Firefox (no shot
test to run them).
Compared 2026-10-17. Not reached by either walk, so not compared here: a group's switch
preview (`_settings_switch.html`, boards B, C and J2; neither walk pressed Its own or Not
applicable) and the mode's switch (J1's Make <network> standalone…, drawn but not pressed).
Compared again 2026-10-18 for C1160, by reading `_network_source.html`'s change against the
regions below and the card as tests/test_network_source_v2.py draws it (`TestWhatNetBoxLeftOut`,
a NetBox network on the shared fake), not from new shots: on a NetBox network at rest, the
status line now also counts the devices loaded with a warning and those no longer in NetBox
("2 devices, 2 skipped, 1 with a warning, 1 no longer in NetBox, read just now."), and under it,
each collapsed with its count, one group per field that skipped devices (its words and where it
is put right, then each device with the inventory's own reason), one per field that warned, and
one for the devices NetBox stopped returning (what refuses them and what stays on this host,
then each device, its address and since when). The stale badge now also reads the status's own stale flag. Today's
banner drew these lists; the 2026-10-10 source line drew none of them, so they are a new
region, a deviation (below). A network on its own list, the change's preview and its result do
not move, so every other verdict stands.

**Compared again 2026-10-27 (PHASE8_PLAN 17.1 S11):** `settings.html` now draws the network's
SDN controllers card (board SdnSettings, `_sdn_settings.html`) at the foot of the Integrations
tab, below the group cards, spanning the tab. The card is compared region by region in its own
record, docs/fidelity/sdn-settings.md, from tests/test_board_shots.py's `test_sdn`
(`sdn-settings-page-1440`); nothing else on the page moved, so every other verdict stands.
Templates compared: templates/v2/settings.html, templates/v2/_settings_scope.html, templates/v2/_settings_mode.html, templates/v2/_settings_card.html, templates/v2/_settings_refused.html, templates/v2/_network_source.html, templates/v2/_network_create.html, templates/v2/_network_delete.html, templates/v2/_network_picker.html, templates/v2/_network_picker_items.html
Templates sha256: `522b41d09272a03d10ad7508be0fc483670041accb734ea6932379a46fa1f8de`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Settings current at the foot | the same (every capture) | **same** |
| Page head | "Settings", the network chosen by a select at the right | "Settings · <network>" with its (i) and a sub-line saying what the network's page holds and that the installation's settings are under Installation (W2 capture 39); the select replaced by the scope bar, as board H redrew it | **same** |
| Scope bar (H) | Installation (every network, what it holds) · Default (the base for N networks that inherit) · a network (its mode) · Choose a network ▾ | the same three parts with their lines ("every network (1) · NetBox, Proxmox, the records database", "the base for the 0 networks that inherit", "W2 walk inherits from Default") and Choose a network (W2 capture 39) | **same** |
| Scope bar's chooser beside the picker | H's chooser, N's picker in the top bar | both drawn alike, and the operator took one for the other in W2 (steps 33 and 35; C1054) | **deviation** (log: Settings: the scope bar's chooser looks like the top bar's picker (C1054)) |
| The mode's banner (I, J1) | "Branch-B is standalone: it takes nothing from Default. Since <when>, <who>." with its switch | "W2 walk inherits from Default." with Make W2 walk standalone… and How (W2 capture 39); no since or who | **same** |
| Tabs | Integrations, Network, Checks, AI, Server, Security posture, Diagnostics | Integrations and Network; the installation's tabs are on Settings › Installation (the sign-off's "Installation (F) is its own page") | **deviation** (log: Settings: a network's page has two tabs, the installation's on its own page) |
| A network's card (A, I) | the group's name, its origin chip, every field's value with where it came from, the three-way choice (Inherit from Default, Its own, Not applicable) | the same: "Grafana", "inherited from Default", the three-way choice with its (i), each field "<value> inherited from Default" or "built-in default, set nowhere", and "Every value here is Default's. A change in Default changes W2 walk's too." (W2 capture 39; W3 capture 12) | **same** |
| Default's card (D, G) | "set here" and "inherited by 12", the field editable, Save and Test; G's list of who inherits, own, not configured and not applicable | "set here" or "unset" and "inherited by 0" as chips, the field, "An empty field keeps what is stored…", Save with its (i), and "Inherited by 0" again at the card's foot (W2 capture 24); no Test on a group that cannot be tested | **deviation** (log: Settings: Default's card says inherited by twice and lists no one (a defect, register C650 follow-up)) |
| G's warning on a Default change | "Change Default's Grafana URL: 12 networks inherit this value…", bound, then the result naming the networks changed | not built: Default's Save writes at once (W2 step 31) | **later** NSOT_P8_DESIGN section 6 step 7's "Left": Default's change with G's warning naming who inherits it |
| Field labels | written labels (URL, API token, Token expires) | made from the keys: "Reads answer cap kib", "Netbox excluded VRFs" (W2 capture 24; C1051) | **deviation** (log: Settings: field labels are made from the keys (C1051)) |
| A structured value | not drawn | Verify settle windows a raw JSON text box (W2 capture 24), read as JSON on an inheriting network (W3 capture 12; C1052) | **deviation** (log: Settings: Verify settle windows is a raw JSON box (C1052)) |
| The saved line | "Saved for Branch by <who> at 04:52 UTC: 5 fields… See the record" in place of the card | in the card: "<group> saved by <you> just now: 1 field (reads_retention_days); every network that inherits <group> reads the new values." naming the key, not the label (W2 capture 24; C1050) | **deviation** (log: Settings: the saved line names keys, not labels (C1050)) |
| A stale save refused | a refusal naming what moved | "Not saved" in place of the card, its title and the value typed lost (C1048); Why "it was '30' when you opened it and is '31' now" for a field that was unset (C1049); Read Default's settings again opening the Integrations tab, not the field's (C1015) (W2 capture 23) | **deviation** (log: Settings: a stale save's refusal replaces the card (C1048, C1049, C1015)) |
| Back to inheriting, one field | "Go back to inheriting from Default…" per group | per group on a network's card (the three-way choice); on Default a field once set cannot go back to unset (W2 step 32; C1053) | **deviation** (log: Settings: a set field has no way back to unset (C1053)) |
| New network… (I, and the 2026-10-10 create line) | "New network": Name, Inherits from Default or Standalone, Create network | from the scope bar's chooser: Name, Preview, then "Create W2 walk: its records live in lists/w2_walk…", Create and Change the name; the network inherits, and its own page offers the switch (W2 steps 33 and 34) | **deviation** (log: Board I's create form and a delete card) |
| The network picker (N) | "Network Branch inherits ▾"; "Find a network (20)"; Recent · yours and All networks · 20, each with its mode as a chip; "this page"; typing narrows | "Network W2 walk ▾"; "Find a network"; each row its name and its mode in words ("recent · the base"); "Your choice is yours alone: it changes no one else's pages." (W2 capture 39); no group headings, no count, the mode not a chip | **deviation** (log: Settings: the network picker's rows carry their mode in words, under no headings) |
| Inventory source (the 2026-10-10 source line) | where its devices come from and how fresh; the change previewed by reading NetBox once; Refresh now | badged "its own list" or "NetBox"; "Its devices are its own list on this host: 0 devices." or "Its devices come from NetBox, filtered by status planned; read every 300 s…" with "0 devices, 0 skipped, read just now."; the fields; Preview the change with How; the preview "From its own list to NetBox… NetBox holds 0 devices for these filters." with Save the source and Cancel; Refresh now with its (i) and "Read from NetBox now: 0 devices, 0 skipped, 0 warnings." (W2 captures 26 and 27; W3 capture 12) | **same** |
| What NetBox left out (C1160) | not drawn: the source line names where its devices come from and how fresh | on a NetBox network at rest, the counts lead (skipped, with a warning, no longer in NetBox); then collapsed groups, each with its count: skipped by field ("1 skipped, not in the inventory: no primary IPv4 address; set one on the device in NetBox"), each device with the inventory's reason; loaded with a warning by field; and "1 no longer in NetBox", what refuses them and what stays on this host, each device with its address and "not returned since" (tests/test_network_source_v2.py's `TestWhatNetBoxLeftOut`; sixty skipped devices draw no name outside a closed group) | **deviation** (log: Settings: the Inventory source card names each skipped, warned and gone device (C1160)) |
| The NetBox fields on its own list | not drawn | with "its own list on this host" chosen, the NetBox filter fields stay editable, still holding "planned" (W2 capture 27, W3 capture 14; C1055) | **deviation** (log: Settings: the NetBox filters stay editable on its own list (C1055)) |
| Delete this network… (the 2026-10-10 delete line) | a preview of what it holds and where its data goes, then the name typed | "Delete W3 walk": "Removes W3 walk from every page; its data is moved aside on this host, never erased. A preview comes first.", Delete this network… with How; the preview (holds, where the data survives, the name typed); the result "W3 walk is deleted: … its data survives at lists_removed/w3_walk-<UTC>…" with Default's settings (W3 capture 41) | **same** |
| The deleted network's page (SettingsNetworkDeleted, the 2026-10-17 line) | the page head, the scope bar marked "deleted: it has left every page", one notice (when, by whom, its data's folder, kept) and nothing to act on; phone width stacked | "Settings · W2 walk", "W2 walk is no longer a network: it has no settings to show or change.", the scope bar with "deleted: it has left every page", one notice naming the time, who, and `lists_removed/<folder>`, kept; nothing to act on; stacked at phone width (W3 captures 01, 02, 43, 47) | **same** |
| The shell on the deleted page | the top bar as on every page | Needs attention's count reads "?" and the Integrations and Update chips are missing (W3 capture 01; C1113) | **deviation** (log: Settings: the deleted page's shell reads "?" and drops its chips (C1113)) |
| A tab drawn before the delete | each write answered in place, refused by name | "Couldn't load this card." with Try again; the reason ("'W3 walk' was deleted at …; its data is at …. Nothing was changed…") only on hover (W3 capture 44; C1119) | **deviation** (log: Settings: a stale tab's refusal hides its reason on hover (C1119)) |
| The top bar's network after a delete | names the network the page's requests go to, never the deleted one as if shown | a fresh load reads "Network Default" (W3 capture 01); the tab where the delete was pressed reads "Network deleted", amber (W3 capture 41) | **same** |
