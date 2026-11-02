# Fidelity: Source of Truth › Intent, the network's layers (board FC's FC2)

The page as built in phase 1 (read-only), compared region by region with its approved board
(C650's step). Read from shots of the board and the page side by side, in the same headless
Firefox, on the browser layout test's lab (`tests/test_profile_apply.py`'s, r2 and r6), given
three committed layers: the network's domain and NTP server, site lab-a's location and tag
blind-lab's account `lab` on r2 (`tests/test_board_shots.py::test_intent_layers`).

Board: `FleetChanges.dc.html` (board FC, revision 2, approved with changes by the operator
2026-11-01, C2283), its region FC2, at 1440. The board draws nine devices and five layers; the
lab here has two devices and three.
Shots: the board at 1440; the page at 1440, 1280 and 390 (`intent-layers-view`), tag
blind-lab chosen as the board draws it.
Compared 2026-11-02.

| Region | Board | Built | Verdict |
|---|---|---|---|
| The head | "Intent · layers" and the precedence line | the same, the network named after it as every Source of Truth page names it | **same** |
| The sidebar | Intent, a new item under SOURCE OF TRUTH | Intent first under SOURCE OF TRUTH | **same** |
| The layers list | rank and slug, "N devices · M values", the chosen one highlighted, in merge order | the same | **same** |
| Add a layer… | a button and its "How does this work?" under the list | not drawn; the head's ⓘ opens the manual page | **later** (phase 2's plan writes a layer) |
| The list's note | "Groups come from NetBox … one file a layer … committed as intent is" | the same, naming the inventory (NetBox's on a NetBox network) | **same** |
| The chosen layer's head | its group, its devices, "read from NetBox 40 s ago" | its group and devices, read on each request, so no age; its file and last commit added | **deviation** (log: Board FC built, phase 1 (c) FC2) |
| The values table | Path, Value, Devices it reaches, "(none overrides it)" | the same; a device that overrides is named with what overrides it | **same** |
| Edit… and Remove… | on each row | not drawn | **later** (phase 2) |
| Secret references | each reference, its state, Set value… (in Credentials) | each reference and what it is for; no state or Set value… | **deviation** (log: Board FC built, phase 1 (c) FC2) |
| The layer's actions | Plan this layer's change…, Add a value…, History of this layer | not drawn | **later** (phase 2; History has no filter by layer file yet) |
| Precedence | stated once, two of one rank refused naming both | the same words | **same** |
| A conflict | the refusal stated in words | listed above the layers with both values and the devices | **same** |
| 1280 and 390 | (the board is drawn at 1440) | the same order; at 390 the list stacks above the chosen layer | **same** |

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

Templates compared: templates/v2/intent_layers.html, templates/v2/_intent_layers.html
Templates sha256: `ea0522f84fadc4629a0d40a5ec0aa8cf781a32d6daa6b9d860b8e1a7cb413988`
(The past-twelve devices list keeps its open state through a live redraw, `data-keep`, C472's
rule; nothing drawn moved.)
(2026-11-02, C2299: the secret references' note says a value is set on each device's Intent
tab, under Secret references, which now lists a layer's references; the words only, the
region's verdict stands. Before: `5c23996f9a068ec27b99cc193d6acd2cab640306c2148d6175f842091d4d167e`.)
