# Fidelity: a fix's own page (2026-11-18)

Boards: `docs/boards/fix-bpdu-guard.html` (artboards 1 and 2: the page as it opens and Run…
pressed; approved by the operator 2026-11-16 with six changes, C3849 pieces 3 and 4; Delete…
and Restore… inside How it runs by the operator's decision the same day) and
`docs/boards/fix-manual-controls.html` (screens 1 and 3: Run on an open incident, Edit… in the
Contents fold; approved 2026-11-16 with two corrections). The page was built in skip mode
(a61bb071, da740aa1, fc937efe, 74303566, 0d669827, 639a6b1f) and is compared here for the first
time, by the skip-mode debt pass (docs/FAST_LANE_DEBT.md).

Shots: the debt pass's own (an untracked shot beside tests/test_board_shots.py, its shots in the
operator's debt folder), on the heal's lab with the BPDU guard fix saved in Dry run from a
verified run (tests/test_saved_plans.py's match and fills): `debt-fix` at 1280 and 390 beside
`debt-fix-board` (fix-bpdu-guard.html whole at 1280 and 390); `debt-fix-set-automatic` at 1280
and 390 (How it runs opened, Set Automatic… and Delete… open) beside
`debt-fix-set-automatic-board` (fix-manual-controls.html whole); `debt-fix-run` at 1280 and 390
(Run… pressed); `debt-fix-edit` at 1280 (Edit… pressed); `debt-fix-builtin` at 1280 (the
built-in errdisable-recover's page). The shots' world holds no committed intent, so Run…'s card
says why it cannot offer a port; its layout is what is compared.
Templates compared: templates/v2/fix.html, templates/v2/_fix_how.html, templates/v2/_fix_run.html, templates/v2/_fix_contents.html, templates/v2/_fix_form.html
Compared again 2026-11-24 (C3860, the operator's review of 2026-11-16): Run… on a fix that
matches no open incident draws one plain message, "No open incident needs this fix right now.",
with "Or choose a device and interface…" (board fix-manual-controls screen 1's own link) and
Close, where it drew that line above a device and interface form; the region is the same card,
narrower in what it holds, as the operator asked, no deviation to log. Compared by the
template's diff and tests/test_fixes_routes_rights.py's browser case, not by new shots.
Templates sha256 before: `3854a50b173d38410725a4952003eb9d9bb18c178bcdfb494ffc6292a6a8d592`.
Templates sha256: `6846e56e47df66e3f90eced5797956d98cca3ae1b43c660c784a527e2e96095e`

Compared again 2026-11-18 (the skip-mode debt's carried-fields pass, 67b90db3): in
`_fix_run.html` the Run button posts to `c.post.url`, which `fix_page.run_card` builds with
`url_for` from the endpoint and arguments the template named before. The info mark's hover
names the whole hash (`pv.hash`) where it named its short form, and the button's own hover still
names the short form. Nothing drawn moves: no element, no words on the page, and no region's
verdict below changes. This was compared by the template's diff, not from new shots. Templates
sha256 before: `6287387518bd3753b23e7d1bbf84632402c46be2c765abc08812093dbfab9445`.

Checked by tests/test_board_fidelity.py since 8e954585 (`"fix.html": "fix.md"` in `RECORDS`).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Breadcrumb | Fixes / Saved / <the fix's name> | the same, Built-in or Deleted for those | **same** |
| The BLUF card | its name and (i), "Recovers …" (what it fixes), the mode's badge and how it runs with its record ("4 runs, all verified"), Run… and its (i), "Saved from incident hi-0412" | the same lines: "Fixes: a switch port err-disabled by BPDU guard, on an access port", Dry run "records what it would do on a matching incident and changes nothing by itself · version 1 · no run recorded", Run…; the saved-from link drawn when the fix was saved from an incident (the shots' fix was saved from a run alone) | **same** |
| The folds | Contents, Origin, Record, How it runs, each folded (artboard 1 draws two open to show what they hold) | the same four, folded | **same** |
| Contents | what it sends in config mode, never saved, as a code block; the parameter said; Checks before; Verifies after | the same, headed "Contents · version 1" (its version, fix-manual-controls screen 3) | **same** |
| Edit… (fix-manual-controls screen 3) | inside Contents: the form in place, "Saved in place (same version)" (name, description, the match) and "A change here saves version 2" (lines, checks, verifies), Save as version 2 and Cancel | the same sections in place in the fold, "Contents · version 1, editing"; the button reads Save until a change makes it a new version | **same** |
| Origin | folded: where it was saved from | the same | **same** |
| Record | one line a run, numbered, its outcome and verify, Open the run; dry-run records counted | the same, "Record · no run recorded" with none | **same** |
| How it runs | the ways a fix runs, this one's marked; what changed it and when; Delete… and Restore… inside it (screen 3) | the same: Automatic, Dry run, Manual only, the fix's marked "(this fix)", Changed; What its checks cannot prove on a port that is down; Delete… with its reason and Delete this fix | **same** |
| Set Automatic… (in How it runs) | not drawn: fix-manual-controls says in words that a fix "can be set Automatic only after its first verified run (the self-healing right)" | a fold inside How it runs: "Version 1 verified on run 2ede0478, Nov 15 03:00. Automatic, it runs by itself on a matching incident while Default's self-healing is in Auto, on your standing approval of this version's plan.", Set Automatic and its (i); "Not yet: <why>" and the button disabled before a verified run; the right a viewer lacks said beside it | **deviation** (log: A fix's Set Automatic…, a control no board draws) |
| Run… (artboard 2, fix-manual-controls screen 1) | the card in place under the BLUF, before the folds: Run on an open incident (each matching incident a choice), Or choose a device and interface…, the program as it will be sent, Checks first, Then verifies, Run on <device> <port> and Cancel | the card in the same place, "Run this fix"; when nothing can be offered it says why with Close (shot `debt-fix-run`: no committed intent in the shots' world) | **same** |
| A built-in's page | not drawn | read-only: no Edit…, How it runs says how it runs from code and the network's settings; a built-in command plan has Run… (the operator, 2026-11-17) | **same** (the board's own words: "A built-in fix is read-only") |
| Phone | not drawn | the folds stack full width; Run…'s card the same | **same** |

**Compared again 2026-11-25 (C3859, the operator, 2026-11-16: "on the fix page, Delete as a
visible secondary button, not hidden inside the How it runs fold"):** by the template diff, not
by new shots. In `_fix_how.html`, Delete… (Restore… for a deleted fix) leaves the How it runs
fold: under it, in the same card, a secondary button opening the same reasoned confirm, its
words, rights and answer unchanged. It opens by itself when the page is opened from a Fixes
row's Delete… (`?delete=1`).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Delete… (C3859) | board fix-bpdu-guard's How it runs fold held Delete… | a visible secondary button under the fold, the same confirm | **deviation** (log: C3859 Delete… visible on the fix page and on each Fixes row) |
