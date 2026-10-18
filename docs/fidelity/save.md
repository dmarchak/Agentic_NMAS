# Fidelity: Devices › Save (7.4's board C)

Devices › Save as built, compared region by region with its approved board. Read from shots of the
board and the page side by side, in the same headless Firefox, on Save's own lab
(`tests/test_save_v2.py`'s `lab`: r2's real capture as its committed golden, r3 answering and not
in the manifest, r4 not answering at the last reachability read, s9 with no driver; the hourly
startup check read r2's accounts not in startup and r3's in it)
(`tests/test_board_shots.py::test_save_page`). Three states, each reached in the page as a person
reaches it: the plan for all four; the result of r2 and r3 confirmed (r2's running moved by the
suite's `_broken`, so its golden is recorded; r3 refused by the manifest, a partial); the whole
network (r2 alone) confirmed, its baseline decided. The run between is the one stepper's, shot by
`test_stepper` and compared in docs/fidelity/stepper.md.

Boards: `SaveAll.dc.html` (board C, drawn at 1080 wide inside the frame) on the "NMAS v2 mockups"
canvas, page "7.4 Fleet…", approved 2026-10-04 (C593; its sign-off: "Its first count is what is
measured, not the board's 'startup differs'"). Board C draws the plan, the run and the result one
under another; the page shows one at a time in the same card. `SaveProgress.dc.html` (C605) draws
the run, compared in docs/fidelity/stepper.md. There is no phone board for Save.
Shots: the board at 1440 and 1280 (`save-board-*`); the page's plan (`save-plan-page-*`) and its
partial result (`save-result-page-*`) at 1440, 1280 and 390, its whole-network result
(`save-fleet-page-*`) at 1440 and 390. The operator's walk W4 (2026-10-17, steps 37 and 38)
captured the plan with its repeated-baseline notice, the run on the stepper and the whole
network's result with its baseline earned (screenshots 41 to 43); read beside the shots, they
draw the same regions.
Compared 2026-10-18.
Templates compared: templates/v2/save.html, templates/v2/_save.html
Templates sha256: `12121a8bbe308b1adea1f7a5c3d3136cbff6273cbbbef431493330d0334b091f`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Devices current | the same | **same** |
| Breadcrumb and header | "Devices › Save"; "Save 480 devices: to startup, and as golden"; How does this work? at the right | the same words and count; the help is the (i) beside the title, as on every v2 page | **same** |
| Sub-line | none | "<network>: each device saves its running config to startup…", which the card's first paragraph says again | **deviation** (log: Save: the sub-line names the network and says what Save does) |
| Before it runs | the heading and the paragraph (write memory, read back, recorded as golden, one commit, running not changed) | the same paragraph | **same** |
| The counts | "312 not saved: startup differs", "164 saved already: recorded only if the golden differs", "4 not answering: left out, named" | what is measured: to save, not answering: left out, held, cannot be saved from here: left out; then the hourly check's line naming what it compares (accounts only) and that the rest of startup is not measured | **deviation** (log: Save: the plan's counts are what is measured) |
| Repeated baseline (C860) | not drawn | the card's leading warn notice when the whole network's save would record the state of the newest baseline again (W4's screenshot 43) | **deviation** (log: C860: v2's Save says when it would repeat the last baseline) |
| The groups | "312 not saved · by site", collapsed; "4 not answering · acc0412, …", each with show | one group per outcome, the first eight names in its summary; the devices to save collapsed, a left-out group of up to 12 open, each row its device and why | **deviation** (log: Save: the plan's groups are by outcome, not by site) |
| Recording without saving | the note, ending "…and says 'not saved to startup' when it is not" | the note without its last clause | **deviation** (log: Save: the note leaves out what Capture says of a device not saved) |
| Footer | Back; Save 476 devices; How does this work? | Back; Save N devices, busy on itself ("Making the plan again and starting…"); the (i); the confirm's statement and the plan's hash it is bound to | **same** |
| The run | Running, in place: the summary, groups, each device on expand | the one stepper in place of the plan (C605), compared with SaveProgress and StepperPhone in docs/fidelity/stepper.md | **same** |
| Result headline | "476 devices: 470 saved and recorded, 6 failed", partial | "2 devices: 1 saved and recorded, 1 not", partial (amber); "1 device: 1 saved and recorded", done (green) | **same** |
| Result's record line | "Commit 9be04d1 (Source: save), as operator@example.com (verified)"; History, filtered to this commit | "Commit <12 hex> (Source: save), as the person who confirmed it."; a History link to the whole timeline | **deviation** (log: Save: the result names no person and its History link is not filtered to the commit (a defect, register C650 follow-up)) |
| Baseline | not drawn | for the whole network: "baseline earned <tag>: every device of <network> was saved and recorded, each at its committed intent", or "No baseline:" with each reason (W4's screenshot 42: earned) | **deviation** (log: Save: the whole network's result says its baseline) |
| Find a device, Outcome | the search and the outcome select | the same, re-asking the job's card | **same** |
| Result groups | failed first, open: each row its words and the difference, a Retry or Retry when free per device, "4 more · show all 6"; running, done by site, waiting | one group per outcome, the failed open with each device linked and its words; no Retry per row and no link to the difference; the saved group's names on one line | **deviation** (log: Save: a failed device's row has no Retry of its own and no link to the difference (a defect, register C650 follow-up)) |
| Retry the failed | "Retry the 6 failed" | "Retry the N not saved", opening Save for them planned again; not reached in the shots (r3's refusal is not retried), compared by `tests/test_save_v2.py`'s read-back test, which renders it | **same** |
| Phone width | no board | at 390 the counts wrap, every group and the footer stay inside the column; nothing runs past the screen (`TestInARealBrowser`'s phone test holds it) | **same** |
</content>
</invoke>
