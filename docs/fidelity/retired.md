# Fidelity: a retired device's address (board 12's last card)

A retired device's address as built (`/v2/device/<name>` once the device has left, C185), compared
region by region with its board. Read from shots of the board and the page side by side, in the
same headless Firefox, on the retire tests' world (`tests/test_retire.py`'s `world` and
`tests/test_device_retire_v2.py`'s `page`: r4 and r5 in 'Lab', a real repository, CSV, manifest
and credential store), r5 retired through the real confirm as that file's test does, its address
then opened, and its Onboard it again… pressed (`tests/test_board_shots.py::test_retired_page`).

Boards: `DevRetire.dc.html` (board 12, Retire) on the "NMAS v2 mockups" canvas, page "Device
actions on v2", signed off 2026-10-03 (NSOT_STAGE7_PLAN, the boards 8 to 12 sign-off); its last
card is this page. The board's card, refusal and result are the device page's Retire, compared in
docs/fidelity/device.md. There is no phone board.
Shots: the board at 1440 and 1280 (`retired-board-*`); the page at 1440, 1280 and 390
(`retired-page-*`), and with Onboard it again… opened at 1440 (`retired-again-page-1440`). The
operator's walk W4 (2026-10-17, step 34) captured the retire's result and the retired record of
the device it retired, and the history its link opens (screenshots 52, 53 and 55), read beside
the shots: the same regions, the same words.
Compared 2026-10-18.
Templates compared: templates/v2/retired.html
Templates sha256: `49c1e42fcf2f34ba273dc4ac7f9c9719283d71eb075565ecbd19f505b99fc84b`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The address | "The last card is the page at /v2/device/r5 once r5 is retired" | the device's own address draws it, never a bare 404 | **same** |
| Sidebar and breadcrumb | Devices current; "Devices / r5" | the same | **same** |
| Header | "r5" and a chip "Retired 2026-10-03" | "r5" in mono, the (i) beside it (as on every v2 page), a chip "Retired" | **same** |
| Sub-line | none: the date is in the chip | "Retired <when> · network <network> · out of management: nothing in Mercury checks, captures or deploys it" | **deviation** (log: Retired: the date is in the sub-line, with the network and what leaving means) |
| No tabs | none drawn | none: the device is in no inventory | **same** |
| Its record | a labelled row, "ITS RECORD" | the card's heading, "Its record", with blank space above and below it out of proportion to the card (W4's screenshot 52 the same) | **deviation** (log: Retired: the record's heading stands in empty space (a defect, register C650 follow-up)) |
| Who and how verified | "Retired by operator@example.com:" (the board's result says "(verified)") | "Retired by <person> (access):", the Actor-Verified trailer's own word, where the other screens say verified | **deviation** (log: Retired: the record says how the person was verified in the trailer's own word (a defect, register C650 follow-up)) |
| The reason | quoted | quoted | **same** |
| The commit | "Commit 4be1a09" as a link; "its last intent and golden are in history" | the commit's first 12 characters, not a link; "…are in history, the parent of that commit" | **deviation** (log: Retired: the retire commit is not a link (a defect, register C650 follow-up)) |
| Its history | "Its history (the same timeline, filtered to r5)", a link | the same words as a button, opening History filtered to the device (W4's screenshot 55) | **same** |
| Onboard it again… | a link | a button with How does this work?, opening Add device in place with the name filled (board E's card) | **deviation** (log: Board E as built) |
| Not an undo | said on the Retire card's What survives, not on this one | "To manage r5 again is onboarding or adopt, not an undo: its credential survives only in the break-glass record." under the actions | **deviation** (log: Retired: the record says again that onboarding it again is not an undo) |
| Phone width | no phone board | at 390 the record wraps and the two actions stack; nothing past the screen | **same** |
</content>
</invoke>
