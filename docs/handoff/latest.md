# Handoff: the week plan, Stage 3 in progress; Stage 1's test changes wait on the operator (2026-11-23, evening)

Read CLAUDE.md, this file and the standing plan, `docs/plan/week-2026-11-23.md`, then
`docs/handoff/OPERATOR.md` (what waits on the operator). docs/handoff/START.md is the standing
prompt. Decisions: `docs/handoff/decisions-2026-11-23.md`. Today's report:
`docs/handoff/reports/2026-11-23.md`. The previous handoff is in git (e201a705's latest.md).

## 1. The blocker: a loop session cannot commit a test change

A session the loop starts has the AppArmor label `unconfined`, so `scripts/nmas-test` cannot make
its network namespace, and the commit hook's red-green (`scripts/nmas-red-green`) says COULD NOT
ASK and refuses any commit that adds or changes a test function. Commits that change no test
function pass. Asked: `OPERATOR.md#session-namespace`. Never `--no-verify`; red-green is a
protected guard. Tests themselves run with `scripts/nmas-test --allow-unconfined`.

## 2. Where the plan stands

- **Stage 1:** C3886 is built and hand-checked but not committed: the work is
  `~/mercury-runs/c3886-keyed-placeholder.patch` (apply on main with `git apply --index`, after
  `git merge` of anything since) and its message `~/mercury-runs/c3886-keyed-placeholder.msg`.
  It is also staged in `~/nmas-worktrees/rulings-gui-kit` (branch rulings/gui-kit at 3f9c6b0d).
  Its independent device-write review was started this evening; the report will be
  `~/Documents/nmas-reports/review-devicewrite-2026-11-24-c3886.md`. C4206 is done (c591f1c6).
  Every other Stage 1 item changes a test, so is BLOCKED on session-namespace.
- **Stage 2:** the serial run started by the previous session died at 16:57 (54%), when that
  session ended. Restarted detached (setsid) at 17:15 in `~/nmas-worktrees/serial` (fdaec024),
  unconfined, logging to `~/mercury-runs/suite/serial.log`, JUnit `serial.xml`; about 80 min.
  Compare with `m.xml` (12 workers, d24cbdc4) by `/tmp/c3886/junit_diff.py` (or rewrite it: it
  parses both JUnit files by test id and prints what differs). Fixes are BLOCKED (tests).
- **Stage 3, in progress:**
  - DONE: `tools/review_screenshots.py` (fd9e6e77): 60 pages, both sizes, in 122 s.
  - Running (background agents, writing only their files, uncommitted): `design/research.md`;
    `design/review/SETTINGS.md`, `design/review/ACTIONS.md`, `design/review/WORST_CARD_PAGES.md`.
  - Next: three proposals in `design/proposals/<letter>-<name>/` (A Workbench: list and detail,
    assistant docked right; B Inbox: a triage queue first, the assistant a command palette;
    C Document: one readable page per object, an outline, the assistant a drawer), each with a
    README and static mockups using `design/proposals/_shared/tokens.css`; then the comparison
    README, the zip, and the question to the operator.

## 3. State

- main is fd9e6e77 (pushed). Nothing deployed. No full suite this session yet.
