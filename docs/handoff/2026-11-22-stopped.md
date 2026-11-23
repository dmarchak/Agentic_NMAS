# Handoff: the unattended run of 2026-11-22, stopped at Phase 0

Read CLAUDE.md, then this file, and nothing else to start (docs/handoff/START.md is the
standing prompt). Decisions taken without the operator: `docs/handoff/decisions-2026-11-22.md`.
Today's report: `docs/handoff/reports/2026-11-22.md`. The previous handoff:
`docs/handoff/2026-11-20.md`.

## 1. State: STOPPED, waiting on the operator

**An automatic session must not resume work: nothing in the plan can move until the operator
decides section 2's question.** Write the day's report and exit (START.md, "Start", step 3).

- **Branch `merge/kit-into-main`** (pushed, 4cdd5d91 + this handoff's commit):
  - 2bef4689: the merge of `lab9-kit-hotfix-2026-11-20` (d3549552) into main (55a3c6b2), with
    every conflict resolved so both sides' behaviours survive;
  - 43a4ca59: a denylisted term on main fixed forward;
  - 4cdd5d91: START.md, the session script and the decisions.
- **main is not moved** (55a3c6b2). Nothing is deployed.
- **Why it stopped.** The full suite on the merge fails 1,260 ids
  (`docs/handoff/phase0-failing-ids-2026-11-22.txt`, each marked). 1,250 of them fail on main by
  itself: main's skip-mode debt, the changes shipped without tests (docs/FAST_LANE_DEBT.md).
  Only 10 are the merge's: 2 were artifacts of the uncommitted index, 1 is fixed (43a4ca59),
  and 7 are SDN tests meeting main's stale AI fakes and its local-time clock. After fixing
  shared causes, what is left asserts behaviour the operator's later decisions removed. Making
  those pass means retiring or rewriting tests, which this run may not do.
- **Suite numbers** (4 workers, about 19 minutes):

  | Tree | Passed | Failed | Errors | Skipped | Time |
  |---|---|---|---|---|---|
  | The merge, 2bef4689 | 30,115 | 1,225 | 35 | 404 | 1,162 s |
  | main alone, 55a3c6b2 | 29,826 | 1,215 | 35 | 406 | 1,152 s |
  | The 64908d37 baseline (the kit, 2 workers) | 27,271 | 0 | – | 346 | 1,527 s |
- **The fix-forward work is saved, not committed:** `~/mercury-runs/phase0-uncommitted-2026-11-22/`
  (outside the repository) holds `tracked.patch` (`git apply`), `untracked.tgz`, `BRIEF.md`, and
  each group's still-failing list.
  - Heal: 209 failing went to 104. The fixes are fakes, a stops check that read the wall clock,
    and missing operation words.
  - Incidents: 354 went to 91.
  - The AI and other groups were stopped part-way.
  - The tgz also holds the Phase 2 design note `docs/design/assistant.md`.
- **Automatic sessions:** `tools/nightly/mercury-session.sh` runs from the operator's user crontab
  at 03:35 America/Denver, with `flock -n` on `~/mercury-runs/session.lock` and its logs in
  `~/mercury-runs/`.

## 2. The operator's decision that unblocks the run

**The way out already exists: `overnight/gui`** (6eca7eec, on origin, 324 commits ahead of
main). It holds the 2026-11-18 debt pass over every skip-mode row (debt-tests-3, debt-fidelity,
debt-context). Its own report lists about 20 standing failures for the operator to decide:
- C3970, "each fact once" (test_incident_titles);
- test_bluf's device-write trigger;
- C3886;
- test_heal_analysis_never_read, a weakening that needs the operator's words;
- C3958, C4085, C3957;
- C4091, the Assistant's place in the v2 walk.

It also carries Test-Weakened commits (retired tests of removed behaviour, each with its row).

Options:
- **(a), recommended:** decide `overnight/gui`'s standing list. Merge `overnight/gui` into main.
  Then merge `merge/kit-into-main` forward onto it and run one full suite.
- **(b):** authorise, for this run, rewriting or retiring tests of removed behaviour, each with a
  registered row and a Test-Weakened trailer. Then the run fixes forward on this branch, starting
  from the saved patch.

## 3. The plan (the operator's, 2026-11-22), unchanged, resumes at Phase 0's end

**Phase 0, merge.** Merge the kit into main on `merge/kit-into-main` (done); one full suite
against 64908d37's numbers; green: fast-forward main and push; red and not fixable without
weakening a test: stop (this state).

**Phase 1, fast suite.** Under 10 minutes locally, the same counts serial and parallel. The
measured lever: about 4,650 worker-seconds a run, the slowest item 62 s; `scripts/nmas-workers`
caps local runs at 4 workers (`MAX_WORKERS`, after the 2026-10-19 OOM) while its memory formula
allows about 17 on a free laptop; about 10 workers would reach 10 minutes. CI already runs five
shards from `scripts/nmas-shards` (not a protected guard), so a ci.yml change may not be needed.

**Phase 2, the AI assistant.** Stage 1 exists (modules/ai/assistant.py, routes/assistant_v2.py,
the panel). The design note (in the saved tgz) builds stage 2 on the read loop with
`fixit_reads.OWN_READS` only (no device read), a server-side thread for persistence, a context
resolver from the page's path, hand-offs to Change it in words and AI troubleshooting.

**Phase 3, GUI usability** and **Phase 4, page performance**: as the operator's plan states;
the whole plan, word for word as given, is section 2 of `docs/handoff/2026-11-22.md`.

## 4. Next

After the operator's decision in section 2: carry out (a) or (b), then one full suite, then
Phase 0's end (fast-forward main, push) and Phase 1.
