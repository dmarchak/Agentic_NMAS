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
| Add a layer… | a button and its "How does this work?" under the list | the button and its ⓘ under the list (and in the empty state), opening the change's form with the new layer's rank and slug (phase 2 (c)) | **same** |
| The list's note | "Groups come from NetBox … one file a layer … committed as intent is" | the same, naming the inventory (NetBox's on a NetBox network) | **same** |
| The chosen layer's head | its group, its devices, "read from NetBox 40 s ago" | its group and devices, read on each request, so no age; its file and last commit added | **deviation** (log: Board FC built, phase 1 (c) FC2) |
| The values table | Path, Value, Devices it reaches, "(none overrides it)" | the same; a device that overrides is named with what overrides it | **same** |
| Edit… | on each row | on each row, opening the change's form with what the layer holds there (phase 2 (c)) | **same** |
| Remove… | on each row | not drawn | **later** (phase 4, after C2228's measurement) |
| Secret references | each reference, its state, Set value… (in Credentials) | each reference and what it is for; no state or Set value… | **deviation** (log: Board FC built, phase 1 (c) FC2) |
| Add a value… | below the values | below the values, opening the change's form with one empty setting (phase 2 (c)) | **same** |
| Plan this layer's change… and History of this layer | beside Add a value… | not drawn: Add a value… and Edit… open the one form that plans | **deviation** (log: Board FC built, phase 2 (c) FC4) |
| FC4: the plan's head | the change's name, the layer, the device count, "plan · nothing sent" | the layer, the device count, "plan · nothing sent" | **deviation** (log: Board FC built, phase 2 (c) FC4) |
| FC4: the counts | "4 devices, 1 group: the same line on each. 0 refused · 0 drifted · the intent change is one commit to layers/tag-blind-lab.yml, made at the approval" | "1 device, 1 group · 0 refused · 0 unchanged", the commit at the approval, and the plan's hash | **deviation** (log: Board FC built, phase 2 (c) FC4) |
| FC4: the line | "+ username lab … from tag blind-lab, layer commit 5a1e2f0" | each group's lines, collapsed past the first, with its devices | **same** |
| FC4: the layer before and after | (not drawn) | the layer now and after, as YAML | **deviation** (log: Board FC built, phase 2 (c) FC4) |
| FC4: canary, batches, stop rule, the step table, Before it can run, the reason, Approve and run | drawn | not drawn: "Approving this plan and running it … is not built yet" | **later** (phase 2 (d)) |
| Precedence | stated once, two of one rank refused naming both | the same words | **same** |
| A conflict | the refusal stated in words | listed above the layers with both values and the devices | **same** |
| 1280 and 390 | (the board is drawn at 1440) | the same order; at 390 the list stacks above the chosen layer | **same** |

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

**Compared again 2026-11-02 (phase 2 (c), board FC4):** the page opens the change's form above
the layers (FC2's Edit…, Add a value…, Add a layer…) and draws the plan's card there
(`_fleet_plan.html`, which joins the templates compared), shot `fleet-plan` (form and plan, at
1440, 1280 and 390) beside FC4 at 1440; the FC4 rows above.

Templates compared: templates/v2/intent_layers.html, templates/v2/_intent_layers.html, templates/v2/_fleet_plan.html
Templates sha256: `945d83b53c66076f1f0b01c3d9034d458237e366bcfcc5ed4e4ac7aa2e4a8005`
(The plan's groups keep their open state, `data-keep`, C472's rule.)
(Before phase 2 (c): `ea0522f84fadc4629a0d40a5ec0aa8cf781a32d6daa6b9d860b8e1a7cb413988`.)
(The past-twelve devices list keeps its open state through a live redraw, `data-keep`, C472's
rule; nothing drawn moved.)
(2026-11-02, C2299: the secret references' note says a value is set on each device's Intent
tab, under Secret references, which now lists a layer's references; the words only, the
region's verdict stands. Before: `5c23996f9a068ec27b99cc193d6acd2cab640306c2148d6175f842091d4d167e`.)
