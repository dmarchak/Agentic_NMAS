# Fidelity: Devices › Change a setting

Devices › Change a setting as built, compared region by region with its board (C650's step),
after the operator's walk W1 (2026-10-16, steps 14 and 15, which changed s1's and s2's intent
through it). Read from shots of the board and the page side by side, in the same headless Firefox
(`tests/test_board_shots.py::test_bulk_intent`), the page fed by test_bulk_intent's lab (four
devices' real fleet intent committed in a real repository, rendered by the real template render
with a stub secret lookup; its fixture's lines inline in the shot) with
tests/test_bulk_intent_v2.py's setting (`logging.settings` losing its source interface) on s1,
s2 and r1, s2's intent drifted so it is refused. Each state reached by its own button: the change
as the Actions menu opens it, its preview, the preview with every group and device opened, and
the commit's result. Read beside them: the operator's W1 captures 14 (the preview of the walk's
description on s1 and s2: 2 devices, 1 group, nothing refused) and 15 (Committed, nothing sent).

Boards: `BulkIntent.dc.html` (1440 wide) on the mockups canvas ("NMAS v2 mockups", page "7.4
Fleet"), board D, "D. change a setting on the selection, each device's diff, grouped", approved
2026-10-04 on canvas v32. The build of 2026-10-10 was made from the board's written description
in NSOT_STAGE7_PLAN 15.4 to 15.6 (the approval log's line of that day); this is the first
comparison with the board itself. It has no phone variant.
Shots: the board at 1440; the change (`bulk-intent-change-page-*`) and the preview
(`bulk-intent-preview-page-*`) at 1440, 1280 and 390; every group and device opened
(`bulk-intent-opened-page-*`) and the result (`bulk-intent-result-page-*`) at 1440 and 390;
each phone shot also as its first screen.
Compared 2026-10-16.
Templates compared: templates/v2/bulk_intent.html, templates/v2/_bulk_intent.html
Templates sha256: `7ad60c127f81518e56763ad52f09a9e6dbb10eeb6aad5467f8595a7da498679c`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar and crumb | Devices current; "Devices › Change a setting on 500 devices" | Devices current; "Devices › Change a setting" | **same** |
| Title | "Change a setting on 500 devices", How does this work? at the right | the same words with the count; the page's help is the (i) beside the title, as on every v2 page (C505) | **same** |
| The lead | "Not an editor: one setting, one new value, and what it does to each device" | the sub-line: one change to their committed intent, checked against what each holds now, committed once, nothing sent | **same** |
| The change's fields | Setting (a select from the intent schema) and Becomes, checked as typed | Path (dotted into the intent document), Holds now and Becomes, values as the intent file writes them, `(absent)` for none; how to write them said above; checked at Preview. A path picked from a list built from the schema is agreed as request R3 | **deviation** (log: Bulk intent on v2 (board D, approved 2026-10-04 on canvas v32, not seen again)) |
| Only where it holds X now | a checkbox, ticked | not a choice: every row's Holds now is required, and a device holding anything else is refused and named (C904 keeps the option when Holds now becomes a display) | **deviation** (log: Bulk intent on v2 (board D, approved 2026-10-04 on canvas v32, not seen again)) |
| Add another setting | a button beside the fields | Add a setting, redrawing the form with what was typed and one more row (up to 12) | **same** |
| The commit's subject | "Why, in one line (the commit's subject)" at the preview's foot | Summary at the change's top, "one line; it becomes the commit's subject", carried to the confirm | **deviation** (log: Bulk intent on v2 (board D, approved 2026-10-04 on canvas v32, not seen again)) |
| Preview heading | "What it does, device by device" | the plan's headline, "2 device(s), 1 group(s), 1 refused" (capture 14: "2 device(s), 1 group(s)"), its "(s)" plurals a C901 copy note | **deviation** (log: Bulk intent: the preview's heading is the plan's headline) |
| Counts | "488 take the change", "9 hold it already", "3 refused: another value" | "2 change, in 1 group by what changes" (capture 14) and "1 refused, unchanged": the count's noun does not agree with its number (C901) | **deviation** (log: Bulk intent: the counts read "2 change, in 1 group" (C901)) |
| Hold it already | its own count and a "no change" group | not drawn: a device whose intent already holds the new value does not hold the row's Holds now, so it is refused, red, as "not what the change expects" | **deviation** (log: Bulk intent: a device already holding the new value is drawn refused (a defect, register C650 follow-up)) |
| Groups | "Group A · 412 devices · the same diff and program", open, its configuration's diff beside what a deploy would send; Group B collapsed; "the 412 devices" | a group per rendered change, collapsed: its count, "group 1: 0 rendered line(s) added, 1 removed" and the first eight names; inside, A deploy would send (masked), No longer rendered, then each device's intent diff on expand | **deviation** (log: Bulk intent on v2 (board D, approved 2026-10-04 on canvas v32, not seen again)) |
| Mode B | "The old server stays on each device until Mode B removes it." | "A deploy is merge-only: these stay on each device until a removal (Mode B) takes them off." | **same** |
| Refused group | "refused 3 · hold another value", open; each device and what it holds in words; each one's Intent tab linked | the badge and names, open when 12 or fewer; a row per device with the reason and, per setting, what the change expects and what it holds, each value drawn as a raw list (`["trap critical", "origin-id hostname", …]`, C901); the device's name is not a link | **deviation** (log: Bulk intent: a refused device is not linked to its Intent tab (a defect, register C650 follow-up)) |
| A group's rows | padded inside their box | the device's name, "No longer rendered" and the merge-only line flush against the box's left edge, the row's rule stopping short of it (`bulk-intent-opened-page-1440`) | **deviation** (log: Bulk intent: a group's table drawn flush against its box (a defect, register C650 follow-up)) |
| The confirm | "Commit to 488 devices' intent" | "Commit the change to 2 devices' intent" (busy on itself), its (i), who confirms, the subject, the preview's hash it is bound to, nothing sent; Change the settings goes back with the rows kept (capture 14) | **same** |
| Result | "Committed to 488 devices", done; one commit e40a771 (a link), Source: bulk-intent, Refused: 3, as the verified person; nothing was sent | "Committed": the devices changed in one commit as the person, the commit's first 12 characters as text with the headline ("7a565becba37; 2 device(s), 1 group(s)" in capture 15), the refused named, nothing sent | **deviation** (log: Bulk intent: the result's commit is not a link (C901)) |
| The next step | Plan a deploy for the 488…, How does this work? | Plan a deploy for these 2… (the batch Apply's page for exactly the changed devices), its (i), Back to Devices (capture 15; the walk's step 16 took it) | **same** |
| Phone | no phone board | the counts stack, the groups and the confirm full width, nothing past the screen | **same** |
