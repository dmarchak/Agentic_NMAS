# Fidelity: Troubleshooting › Fixes (2026-11-18)

Boards: `docs/boards/fixes-list.html` (screen 1, the default view at 1280; revised 2026-11-16,
approved by the operator 2026-11-16 with three conditions, C3849 piece 2) and
`docs/boards/fix-manual-controls.html` screen 2 (New fix… pressed, approved by the operator
2026-11-16 with two corrections). The page was built in skip mode (a61bb071, da740aa1, cf4018c2,
74303566, 1e514200) and is compared here for the first time, by the skip-mode debt pass
(docs/FAST_LANE_DEBT.md).

Shots: the debt pass's own (an untracked shot beside tests/test_board_shots.py, its shots in the
operator's debt folder): `debt-fixes` at 1280 and 390 beside `debt-fixes-board` (fixes-list.html
shot whole at 1280 and 390), `debt-fixes-sorted` at 1280 (Name's header pressed), and
`debt-fixes-new` at 1280 (New fix… pressed), on the heal's lab (Default marked lab, in dry run)
with one saved fix (tests/test_saved_plans.py's BPDU guard match and fills, saved in Dry run from
a verified errdisable-recover run) and Mercury's 17 built-ins.
Templates compared: templates/v2/fixes.html, templates/v2/_macros.html
Compared again 2026-11-24 (the week plan's Stage 5, every setting's description): `_macros.html` gains the `setting_desc` macro, which only the Settings screens call; `fixes.html` calls none of it, so nothing on this page moves and no region's verdict changed. Compared by the templates' diff, not by new shots. Templates sha256 before: `8ee5ab408ce7c561531c2fd7f8a615dcbc1c2ba33ac2e2443760012b74daefa3`.
Compared again 2026-11-26 (Stage 5 step 6): a background read not read yet, or whose stored value cannot be read, says so in one set of plain words on every page (`not_read_yet`, `read_unreadable` in _macros.html: "The DHCP server has not been read yet. Mercury reads it every 5 minutes, and this fills itself when it has."), where each page named its reader and a product. No region moves; every verdict is unchanged. Templates sha256 before:
`d05390ff88fe3bd35bdafbc66d1a471b916fa6eb079ba4d936fbb718c240206f`.
Compared again 2026-11-26 (Stage 5 step 6): the logs not read yet are said in the one set of words every page uses (`not_read_yet`: "r3's logs have not been read yet: the last attempt failed, ... Not the same as r3 having sent nothing."), where it said "Reading Loki: Mercury's logs reader has not read it yet"; the macro's cadence is optional, unsaid where the page does not know it. Every verdict unchanged. Templates sha256 before:
`2acf1d18db8a27e15c53bc3179eaa56bc97fe49d6534a8dbb399746047f4c157`.
Templates sha256: `154dfc9cfaa8cb28dbd29f593ba191c6d1ba0fe2da3200bc7e3ef535c1368ee6`

`_macros.html` is folded in here (a61bb071 changed it for this page; it was in no record); every
page draws it, so a change to it asks for this page to be compared again.

**Not yet checked by tests/test_board_fidelity.py:** `fixes.html` is on tests/signed_off_screens.py's
list but not in that file's `RECORDS`; the line `"fixes.html": "fixes.md",` there makes the check
hold this record (a test change, left to the test pass).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is | Troubleshooting › Fixes in the sidebar, after Incidents, before Self-healing | the same (`base.html`, a61bb071) | **same** |
| Heading | "Fixes" and its (i) | the same | **same** |
| New fix… | none: "a fix is saved from an incident's 'Save this fix' card, so the page has no New button" (screen 1); New fix… at the head's right on fix-manual-controls screen 2 | New fix… at the head's right with its (i) (da740aa1, the operator's manual controls of 2026-11-16, which supersede screen 1's note) | **same** (fix-manual-controls screen 2) |
| The summary line | "6 fixes · 2 saved (1 Automatic, 1 Manual only) · 4 built-in · checked 12 s ago" | "18 fixes · 1 saved (1 Dry run) · 17 built-in": the same counts by mode, no age | **deviation** (log: Troubleshooting › Fixes: one sortable table, not the Saved and Built-in groups) |
| Search or filter… | one link opening search and the filters | the same, the search and the Saved, Built-in and Deleted filters behind it, filtered on the server | **same** |
| The list | two cards, Saved and Built-in, each row three lines (name · what it fixes · how it runs and its record) with its mode's badge first and "last <time>" at its right | one table, sortable by any header (kept in this browser only), columns Name, Mode, Source, Fixes, Runs, Last run; its default order Mode, then Last run newest first; one line a fix | **deviation** (log: Troubleshooting › Fixes: one sortable table, not the Saved and Built-in groups) |
| A row's name | a link to the fix's own page | the same | **same** |
| A row's mode | Automatic, Dry run, Manual only as a badge | the same badges, Off for a built-in its network turns off | **same** |
| A row's source | "saved from an AI plan Sam approved", "from campus's fix kinds" in its third line | the Source column: "Person", "AI", "Mercury built-in" | **deviation** (log: Troubleshooting › Fixes: one sortable table, not the Saved and Built-in groups) |
| A row's record | "4 runs, all verified", "2 dry-run records, nothing changed" | the Runs column: "0 healed", "1 · 1 verified" (runs · verified), and Last run's time or "never" | **deviation** (log: Troubleshooting › Fixes: one sortable table, not the Saved and Built-in groups) |
| A row's words | "Fixes: an access port err-disabled by BPDU guard, once the BPDU source is gone" | the Fixes column in the fix's own words; two built-ins read "its telemetry telemetry-lost" (a condition's key drawn as words; registered by the debt pass), "its telemetry lost" since C4032 (2026-11-24: each condition said by `bluf.TABLE`'s plain words) | **same** |
| Large fleets | the groups collapse, each its first 20 rows, the rest counted | the table's first rows and the rest counted under it (`fix_page.LIST_SHOWN`) | **same** |
| Sorting | not drawn | a header pressed sorts by its column, ▲ or ▼ beside it (shot `debt-fixes-sorted`: by Name, ascending) | **deviation** (log: Troubleshooting › Fixes: one sortable table, not the Saved and Built-in groups) |
| New fix…'s form (fix-manual-controls screen 2) | the form in place under the head: Name, Description, What it fixes, Sends (a shape per line, Add a line…), Checks before, Verifies after, the preview on an example, Save as Manual only and Cancel; New fix… busy on itself while the form is open | the same sections in the same order, above the summary line; Save as Manual only disabled until a name and a line are given, saying so; New fix… not drawn busy while the form is open | **deviation** (log: Fixes: New fix… is not drawn busy while its form is open) |
| Phone | not drawn | the table scrolls inside its card; the head, the summary and the link stack | **same** |

**Compared again 2026-11-25 (C3859, the operator, 2026-11-16: "Delete on every row of the Fixes
list, not only on the fix page"):** by the template diff, not by new shots. In `fixes.html`, a
saved fix's Name cell gains, after its name, a small **Delete…** link (**Restore…** for a
deleted fix) opening the fix's page with its reasoned confirm open; a built-in fix's row has
none (a built-in fix is read-only). No column is added; the sort keys are unchanged.

| Region | Board | Built | Verdict |
|---|---|---|---|
| A row's Delete… (C3859) | the board's rows draw no Delete | Delete… beside a saved fix's name, opening its page's confirm | **deviation** (log: C3859 Delete… visible on the fix page and on each Fixes row) |
