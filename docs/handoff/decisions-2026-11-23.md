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
- The full suite on 77bef647 (4 workers, 1,515 s): 32,166 passed, 19 failed: the rulings file's 12 and 7 order-dependent (C4199), fixed in 120abc10: test_attribution_b2's clock set from each test's start (an import-time `NOW` whose window ended in a run past 13 minutes), and three files' pages computed from their sources alone (`tests/attention_alone.no_stored_incidents`), shown able to fail with a planted incident; the test leaving the incident is C4200 (UNKNOWN: no session `incidents.json` changed across the 41 edge-b files) | the victims assert their planted sources only | revert 120abc10.
- The full suite on 120abc10 (4 workers, 1,516 s): 32,173 passed, 12 failed, 68 skipped: exactly the rulings file's 12; main fast-forwarded from 55a3c6b2 to 120abc10 and pushed; nothing deployed (not fully green) | the operator's condition for moving main | `git push origin 55a3c6b2:main --force` would rewrite published history, so a revert commit instead.
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

## Phase 1, the fast suite

- `scripts/nmas-workers` `MAX_WORKERS` 4 to 12 for local runs (bd1cd9ae, C4201), with tests/test_nmas_workers.py's laptop case and its CI case (`min(4, workers)`, CI's own `--cap 4`) updated under Test-Weakened trailers | the operator's Phase 1 of 2026-11-22, "a fast suite: under 10 minutes locally"; measured, 11 workers 913 s, its lowest MemAvailable 5.0 GiB; CI's sizing, the operator's 2026-11-12 record, unchanged | revert bd1cd9ae.
- test_ai_never parses each product file once a run (bd1cd9ae): 627 to 11 worker-seconds, no assertion changed | the largest single cost in the run | revert bd1cd9ae.
- test_mercury_cli compares the printed verdict with the one the command computed (0b27eee9, C4202): its second check timed a mutant out at the gate's 0.5 s floor under 12 workers' load | Phase 1's same counts serial and parallel; the product's bound is unchanged | revert 0b27eee9.
- The full run on bd1cd9ae at 12 workers: 846 s, 32,173 passed, 13 failed (the rulings file's 12 and C4202's, fixed in 0b27eee9); main stays at bdfb1f95 until a run of the head shows the rulings file's 12 alone | the operator's condition for moving main | none.

## The operator's rulings of the evening (2026-11-23)

- The operator's message: keep working through the plan until the 02:30 handover; their rulings 1 to 5; the order rulings 1 to 3, then the device-write reviews and merges, then one full suite, a deploy if fully green, then Phases 1 to 4 | recorded | none (the operator's).
- Ruling 1, C3970 (cfe043d8): where a fix's own stage failed, the stage says the reason once and the card's status line says the state with a "Why: the stage that failed" link; every other wait keeps its reason on its line | the operator: "keep both rules. The reason is stated once, where the person has to act; other places link to it instead of repeating it. Fix the code"; the stage is where the test (UI_RULES) places the one statement, and the card's line, with its action, links to it | revert cfe043d8.
- Ruling 2, test_heal_analysis_never_read (bd09416f, C4203): the heal loop reads the runners' records (`nsot.run_links`, the attempts moved there), the notifier tells graces and keeps "told" itself (`heal_notice.run_graces`), `key_of` in `heal.keys`; `verified_fix` no longer checks the fix-it section's state, only the newest run's own record | the operator: "fix the code as you recommend" | revert bd09416f.
