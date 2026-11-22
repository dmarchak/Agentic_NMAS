# Handoff: the unattended run that began 2026-11-22

Read CLAUDE.md, then this file, and nothing else to start (docs/handoff/START.md is the
standing prompt). Decisions taken without the operator: `docs/handoff/decisions-2026-11-22.md`.
The previous handoff: `docs/handoff/2026-11-20.md`.

## 1. State (updated at each phase's end)

- **Phase in progress:** Phase 0. The merge is committed on `merge/kit-into-main`: 2bef4689
  (parents 55a3c6b2, d3549552), then 43a4ca59 (a denylisted term fixed forward) and the
  handoff commit. main is not moved.
- **The full suite** (4 workers, about 19 minutes; the command is in section 3): on the merge
  30,115 passed, 1,225 failed, 35 errors, 404 skipped; on main alone 29,826 passed, 1,215
  failed, 35 errors, 406 skipped. 1,250 of the merge's 1,260 failing ids are main's own (its
  skip-mode debt, docs/FAST_LANE_DEBT.md); the merge's own 10 are listed in the decisions file.
  64908d37's baseline was 27,271 / 0 / 346; main has about 2,850 more tests.
- **Biggest shared causes on main** (junit clusters): test fakes behind main's signatures, the
  `restarts.explained_by` fake without `planned=` (211 tests), AI `send()` fakes without
  `progress=` (about 90), a session fake's `post()` without `stream=` (55); removed names still
  tested (`read_loop.MAX_ROUNDS`, `AI_READ_CAP`, `LoopFeature(rounds=)`); `pipeline._read_like_before`
  flagged by the device-send scan (30).
- **Automatic sessions:** `tools/nightly/mercury-session.sh` from the operator's user crontab at
  03:35 America/Denver (the host's zone), `flock -n` on `~/mercury-runs/session.lock`, logs in
  `~/mercury-runs/<yyyy-mm-dd>.log`. Dry-run passed 2026-11-22 21:52 UTC.
- **Nothing deployed.** No deploy in this plan: the operator deploys.

## 2. The plan (the operator's, 2026-11-22), in order

Each phase: commit; update this file; one full suite at its end. A phase that cannot go green
has its uncommitted work reverted, why recorded, and the run goes on to the next, except
Phase 0, whose red stops the run.

**Phase 0, merge.** Read 6f023dc3 (C4191's fix) and record problems in decisions. Merge
`lab9-kit-hotfix-2026-11-20` into main on `merge/kit-into-main` (merge, never rebase or squash),
conflicts resolved so both behaviours survive, each listed in decisions. One full suite against
64908d37's numbers. Green: fast-forward main and push. Red and not fixable without weakening a
test: stop the run, failures written here.

**Phase 1, fast suite.** Under 10 minutes locally, the same pass, fail and skip counts serial
and parallel (xdist; fix tests that share state). ci.yml is protected: write the change it
would need here for the operator. From then on use the fast run.

**Phase 2, the AI assistant (build it).** A right-docked panel from the toolbar, persistent
across pages, aware of the current page, device and incident. Answers from the manual (the
relevant sections only) and the read-only tools a person has, reusing the B4 read loop and the
AI gateway. Every answer shows its sources with Open links, the model and the cost. A change
request is handed to the existing gated flows (intent in words, the AI fix plan); the assistant
never applies a change or touches a device. It logs a manual gap when it cannot answer. Marked
as AI, greyed out when AI is off, no model call until asked, every call in History. Tests cover
all of it with the model mocked; no live model call in this run. A one-page design note:
`docs/design/assistant.md`.

**Phase 3, GUI usability.** `tools/review_screenshots.py` (Playwright, Python) against a local
instance with fixture data, never production; a throwaway local user, its random password held
only in memory; every page and tab at 1920x1080 and 1366x768, into `design/review/shots/`
(gitignored). Settings first: `design/review/SETTINGS.md`, every setting (where, key, what reads
it, type, default), public-safe; Settings restructured into Me / Network / Automation / AI /
System with a search box and a one-line description on every setting; a toggle where a card
holds only on/off; settings read by nothing listed in decisions, code left alone; every key and
behaviour unchanged, and a test that every setting is reachable from the new layout. Then each
page against the rubric: the answer visible in 5 s without scrolling at 1366x768; one home per
task; right-sized controls; plain language; one layout pattern; refresh never loses state. Fix
what fails, re-capture, and write `design/review/index.md` (before and after, one line a page).

**Phase 4, page performance.** Playwright: load time and time to main content for every page.
Fix the slowest (N+1 queries, blocking calls, oversized payloads). The before and after table
goes here.

**At the end.** Copy this file to `docs/handoff/2026-11-22.md` and rewrite it; write
`design/review/shots.zip` (gitignored); the final report (30 lines or fewer): each phase done,
partial or reverted; suite numbers and time; the assistant's test count; Settings before and
after; the three biggest GUI changes; the performance table; the path to shots.zip.

**Standing rules for the run:** START.md's (run rules, deploy rules, the 02:30 handover, the
daily report in `docs/handoff/reports/<yyyy-mm-dd>.md`).

## 3. Next

Phase 0: fix main's own failures and the merge's 8 left on `merge/kit-into-main`, by shared
cause, never weakening a test (an expectation changes only where a commit or debt row states
the new behaviour as the operator's, cited); then one full suite; green: fast-forward main to
the branch and push.

The full-suite command (from the repository root; results in `~/mercury-runs/suite/`):
`env --default-signal=INT,QUIT NMAS_TEST_TIMEOUT=5400 scripts/nmas-test --allow-unconfined -n 4
--dist worksteal -p no:cacheprovider -q -rfE --junitxml=$HOME/mercury-runs/suite/<name>.xml`.
