# Rulings needed: overnight/gui's standing failures left failing

The operator's policy of 2026-11-23: a failure whose behaviour change a record shows the operator
decided has its test updated or retired (Test-Weakened, a row); one with no record that looks
accidental has its code fixed; one that is unclear or needs the operator's words stays failing
and is listed here. The rulings made are one line each in `docs/handoff/decisions-2026-11-23.md`.
Measured on `integrate/gui-kit-main` (overnight/gui with merge/kit-into-main merged on it).

**Ruled by the operator, 2026-11-23 (evening):**
- Section 1, C3970: done (cfe043d8).
- Section 2, test_heal_analysis_never_read: done (bd09416f, C4203).
- Section 3, C3886: **back to you.** The fix (7d68fbf3) was reverted (f68d4f18) before any
  deploy. Its device-write review found a HIGH (C4204): the engine's masked answers hide a
  difference only in a secret's value, so a failed save of a healed secret read as held. My
  measurement had used fixtures that were already masked. Choosing how the save check judges
  running against startup without a session of its own touches your rule that every read is
  recorded and masked. The review's three options:
  1. judge the raw text inside the reads engine, keeping only the verdict;
  2. compare a digest of each secret line;
  3. leave the act its own raw read (today's code: right verdict, two sessions).
  - Recommendation: option 1, a verdict the engine computes on raw text and records masked.
- Section 4, C4090: **left failing, its row open.** The records it needs live in the host's
  data store, and the agent's reads of it are refused by the config-read hook
  (`scripts/hooks/claude-no-raw-config-reads`). `scripts/nmas-config-read` reads goldens and
  configs only. Capturing them needs a masked reader for heal and fix-it records, or the
  operator's own capture; the kit's lab hardware is not what blocks it.

## 1. C3970: each fact once on the incident page (8 tests)

- **Tests:** `tests/test_incident_titles.py::TestEachFactOnce::test_a_failure_is_said_once[failed, partial, refused, rolled_back, symptom_remains]` and `::test_a_failed_verify_says_it_once_and_its_sentence_once[failed, partial, symptom_remains]`.
- **Checks:** a failure's sentence is said once on the page, by the stage that failed (docs/UI_RULES.md, "each fact once"; C3454).
- **Code now:** the card's status line ("It needs a person: <reason>.", `incident_page.py`, from `waits_words`) repeats the failed step's whole sentence, which the stage under What Mercury has done also says.
- **Commit:** c4948c2c "… every 'waits for a person' says why …" (2026-11-15); `waits_words` quotes the operator, 2026-11-16: "every 'waits for a person' … states its reason in plain words; never a reasonless line". Two of the operator's rules collide.
- **Recommendation:** fix the code: the status line says the state and where the reason is ("It needs a person: the fix did not verify; What Mercury has done says why"), and the stage keeps the sentence. It needs your word on whether that short reason satisfies "states its reason".

## 2. test_heal_analysis_never_read (2 tests)

- **Tests:** `tests/test_heal_analysis_never_read.py::test_no_module_of_the_heal_loop_reads_the_analysis`, `::test_the_runner_starts_the_notifier_and_reads_nothing_back`.
- **Checks:** no heal-loop module reads the AI's record or the notifier's answer (docs/HEAL_TO_INTENT.md section 12; the operator's order of 2026-11-12, "Section 12's rule stays in force").
- **Code now:** `heal/detect.py` `_grace_started` reads `heal_notice`'s "sent"; `detect.verified_fix` imports `modules.fixit.incident`; `heal/retry.py` imports `modules.fixit.auto.key_of`.
- **Commits:** 106c117d "Self-healing has no time-based holds … the configuration grace is a named person's decision"; 3d3a8297 "an incident closes on its verified fix"; 9f62b2c7 "a failed fix is retried once per trigger" (all 2026-11-15, skip mode).
- **Recommendation:** fix the code: move `key_of` to a neutral module, read the run's outcome from the runner's record, and record "told" on the incident (the rule kept; the operator named this one as needing their words).

## 3. C3886: the heal act's one apply path (1 test)

- **Test:** `tests/test_heal_act.py::TestOneApplyPath::test_the_act_reaches_a_device_only_through_the_plan_and_the_apply`.
- **Checks:** the heal act reaches a device only through `apply_batch` and `plan_devices`.
- **Code now:** the confirm's save check opens its own session under the hold (`act.py`, `with_temp_connection` → `reload_op.read_boot_pair`: running, startup, `dir nvram:`), outside the reads engine.
- **Commit:** 7d54cf24 "Only a healed heal closes an incident … confirm-first reads the device before any AI call and closes only with proof" (2026-11-16; the operator's "only healed closes").
- **Recommendation:** fix the code: one engine read on the hold's session for both checks, after the offline measurement (largest running and startup against `reads.cap_bytes`; masked against raw verdicts). It is on the device-write path, so it needs its independent review.

## 4. C4090: ten v2 loops drawn by no fixture (1 test)

- **Test:** `tests/test_v2_context_is_drawn.py::TestTheFixturesReachTheState::test_every_loop_drew_or_is_declared`.
- **Checks:** every v2 template loop draws its body in the walk or a provider, or is declared empty in `EMPTY_IN_FIXTURE`.
- **Code now:** ten loops in `_fixit_section.html` (`F.more`, `C.tail.steps`, `lines.verify`, `part.actions`, `part.lines`, `parts`, `st.checked`) and `_inc_proof.html` (`P.checks`, `P.net_zero.lines`, `P.reads`) draw in none.
- **Commits:** the fast lane's incident card and proof work (00c70e0f "Fixed shows its proof …", 3a659d6b "every matching fix is a button on the incident", 2026-11-16).
- **Recommendation:** update the test's fixtures: a provider per loop from a real captured record of its kind (none is captured yet). Declaring them in `EMPTY_IN_FIXTURE` instead raises a list that only shrinks, which needs the operator's words.

## Count

4 rulings (12 tests): fix the code 3 (C3970, test_heal_analysis_never_read, C3886); update the
test 1 (C4090); retire the test 0.
