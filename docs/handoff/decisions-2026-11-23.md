# Decisions, the run of 2026-11-23

One line each: decision | why (the record) | how to reverse.

## The operator's decisions of 2026-11-23 (recorded)

- Option (a): overnight/gui's standing failures are ruled one cause at a time, overnight/gui is merged into main on a branch, merge/kit-into-main merged on top, one full suite; main moves only if the failures left are the rulings file's; no deploy until the suite is fully green | the operator's message of 2026-11-23 | none (the operator's).
- The ruling policy: a behaviour change a record shows the operator decided has its test updated or retired (Test-Weakened and a row, citing the record); no record and accidental is a regression, its code fixed; unclear or needing the operator's words stays failing, listed in docs/handoff/rulings-overnight-gui.md | the same message | none.
- Phase 2: the assistant reads with the same read-only tools a person has, device reads included (show, ping, traceroute, the B4 read loop's tools), through Mercury's tools, never gated, each recorded in History as a person's; only device changes go through the gated hand-off flows; docs/design/assistant.md's "OWN_READS only (no device read)" is withdrawn | the same message | none (the operator's).

## The merge

- overnight/gui (6eca7eec) reaches main by fast-forward (main 55a3c6b2 is its ancestor); integrate/gui-kit-main starts there and merges merge/kit-into-main as its one merge commit (40e88747) | no second merge commit is needed | redo the merge from overnight/gui.
- Five conflicts resolved: section.py's docstring and v2_context's comment keep overnight/gui's text (both sides made the same change); the confirm-buttons count is both sides' cases, 107; the approval log keeps both sides' rows; the register keeps overnight/gui's Count history with a new recount, and C3930's later kit text (overnight/gui's older copy dropped) | each side's behaviour kept, one row per id | per hunk.
- overnight/fastlane-retire's 21 later commits, rulings-words and rulings-close-2 are not merged; only 109189bc (C4091) is cherry-picked, as its failure is on the list | the operator named overnight/gui; those branches hold device-write commits whose reviews are owed | merge them later.
- The full suite on 40e88747 (4 workers, 1,493 s): 32,146 passed, 36 failed: 19 overnight/gui's list, 10 the merge's own (fixed forward in e065afb0, C4198: the kit's SDN tests' premises corrected to the viewer-zone clock from the 2026-11-22 saved patch, the fixit schemas written again in the kit's argument order, `tools/*` claimed, two waits declared, the sdn record hashed again with its shots owed), and 7 that pass alone (an order dependence, judged by the next full suite) | the kit's and overnight/gui's later decisions each kept | revert e065afb0.
- The two 6f023dc3 problems are C4195 and C4196 (C); the public-term fix in 43a4ca59 is C4197, closed (fixed forward); the rows rode in e065afb0 with the fix-forward's own row | the operator's item 3 | none.
- The first full-suite start was stopped at about 2 minutes: nmas-test's default 300 s session bound would have ended it; rerun with NMAS_TEST_TIMEOUT=2900 | the last measured run took 1,162 s | none.

## The rulings (overnight/gui's standing failures, CI #1930 on 6eca7eec)

- C4091 (test_v2_context_is_drawn, the Assistant panel): 109189bc cherry-picked, the one UNREACHED entry | the operator's words of 2026-11-18, "declare the Assistant panel in UNREACHED … I authorize that one entry only", in its Test-Weakened trailer | revert 75564153.
- C3957 (test_sdn_authority): a NOT_DIRECT declaration of `fixit_v2.fix_with_script`, naming the runner's refusal | the operator's ruling 1 of 2026-11-18, "Keep b2aac483" (the runner's authority refusal) | revert 0252cea6.
- C4085 (test_v2_one_confirm): the scan's blind spot fixed (it expands `press(...)` calls); no product change | no behaviour changed: the drawn control already had the pattern | revert ac791fa3.
- C3958 (test_fixit_preview's reserve test): rewritten to the room pass 1 leaves (Test-Weakened) | 7b0bb884, the operator's decision of 2026-11-16, "remove every AI token/size limit Mercury sets itself" | revert 03906fb8.
- C4193 (test_ai_troubleshoot_control's row test): updated: a failed start is said on the incident page, and the row carries no AI status (Test-Weakened) | 00c70e0f, the operator's rule of 2026-11-16, "a status not from the AI never starts 'AI:'" | revert a225f11f.
- C4194 (test_bluf, 2 tests): the code fixed: the err-disable syslog kind is its own unconfirmed condition, which no saved fix may match | no record asks for the gap (7cc49a1b added the kind without a condition) | revert 9f456d31.
- C3970 (test_incident_titles, 8 tests): left failing, in the rulings file | two of the operator's rules collide ("every wait for a person states its reason" and "each fact once") | rule it.
- test_heal_analysis_never_read (2 tests): left failing, in the rulings file | the operator named it as needing their words | rule it.
- C3886 (test_heal_act's one apply path): left failing, in the rulings file | its fix is on the device-write path and needs a measurement first | rule it.
- C4090 (test_v2_context_is_drawn's ten loops): left failing, in the rulings file | each needs a real captured record, or a list that only shrinks raised | rule it.
