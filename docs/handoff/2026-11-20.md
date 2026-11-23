# Handoff, for the session starting Sunday 2026-11-22

Written 2026-11-20 ~23:0x UTC. Read CLAUDE.md, then this file, and nothing else to start.

## 1. State

- **Branch:** `lab9-kit-hotfix-2026-11-20` at `6f023dc3` (worktree `<home>/nmas-worktrees/lab9-kit-hotfix-1120`), plus this handoff's commit. Pushed.
- **Lab kit pin:** `64908d37` (the laptop kit at `<home>/nmas-sdn-lab`; Mercury stopped or as the operator left it).
- **main:** `55a3c6b2` (2026-11-16). The branch is 41 commits ahead and main is not its ancestor: a merge, not a fast-forward.
- **Last full suite:** `64908d37`: 27,271 passed, 0 failed, 346 skipped (1,527 s, two workers, SIGINT and SIGQUIT reset). Nothing later has a full suite: 7437d140's run was stopped part-way, and 6f023dc3's never started.
- **Unmerged, after 64908d37 (not on the kit):**
  - `37e377db`: a confirmed scan proposed as a 20 pps rate limit; every allowed action on the card, a drop only where the protected set allows it; the target's replies join the scan; the 200 B High packet rate cut. Reviewed: no wrong write; finding 1 fixed in 7437d140, the rest registered (C4188 to C4190).
  - `7437d140`: replies with unnamed destinations must mirror the scanner's rate. Reviewed: one hole, C4191, fixed in 6f023dc3.
  - `6f023dc3`: one target per scan. **Not reviewed; no full suite.**
  - The kit's own fixes from 94fa79c8 to 64908d37 are on the kit and reviewed (three rounds).
- **Running or half-done:** none. No suite, agent, deploy or repin is running.

## 2. Closed

- The course's Lab 9 is submitted and closed (2026-11-20). The kit pin no longer constrains work.
- Submitted code package: `<home>/lab9-submission/`: the full zip `lab9-code-group1.zip` (376 files, `code/CODE-INDEX.md`), the slim zip `lab9-code-group1-slim.zip` (30 files, `slim/README.md`), Part B at 64908d37.

## 3. Open C rows from the Lab 9 work

- C4141: the flood rule's words for an idle port hide the 10 pps baseline floor that sets its limit.
- C4188: the High packet rate fallback's 200 B cut misses a padded scan or one sharing its port with bulk traffic.
- C4189: a response's other actions are read once, when it is proposed, never again.
- C4190: on a switch whose meters take no packets a second, AUTO's answer to a confirmed scan goes to a person.
- C4191: a second host of a scanned subnet at the scanner's rate taken as replies (fixed in 6f023dc3; closes when it merges).
- C4192 (queue item 22, registered with this commit): the flood rule's hold is carried across loop runs.

## 4. Plan to 2026-11-30, in order

a. **Merge** `lab9-kit-hotfix-2026-11-20` into main (merge forward, every merged commit's trailers in the message); one full suite on the result.
b. **Fast suite** (C4184): under 10 minutes wall-clock. Measure (wall time, cores, `--durations=100`); xdist with every non-isolated test isolated, never skipped, deleted or loosened; fake clocks where the meaning is unchanged; the same pass count serial and parallel, three parallel runs with no flake. CI sharding is proposed only: a `ci.yml` change needs the operator's exact words.
c. **Toolbar AI assistant:** an inventory of what to reuse, then mockups and a one-page design note; wait for approval before building. The design points:
   - a right-docked panel opened from the toolbar, persistent across pages, aware of the current page, device or incident;
   - answers from the manual (relevant sections only) and from the same read-only tools a person has, reusing the B4 read loop and the AI gateway;
   - cites its sources with Open links, the model and the cost;
   - a change request hands off to the existing gated flows (intent in words, the AI fix plan), never applied by the assistant;
   - logs a manual gap when it cannot answer;
   - marked as AI, greyed out when AI is off, no call until asked, every call in History.
d. **GUI usability review:**
   - screenshots of every page into `design/review/`, by `tools/review_screenshots.py` (neither exists yet);
   - a Settings inventory, `design/review/SETTINGS.md`: every setting, where it lives, what reads it, its type and current value, and "read by nothing" where that is true.
   - The operator's adviser reviews them, and the Settings navigation board is approved before any UI change.

## 5. Working pattern from now on

- One fresh session per day. Each starts by reading CLAUDE.md and this file only, and ends by rewriting this file, keeping the previous one as `docs/handoff/<yyyy-mm-dd>.md`.
- Opus for routine work; Fable for the merge, the assistant's build and debugging. Keep reports short.
- **Standing rules:**
  - tests are never weakened or skipped;
  - one full suite before any deploy;
  - deploy only through `nmas-deploy`, never 02:30 to 03:30 America/Denver, and tell the operator before every deploy;
  - no steps, gates or safety measures the operator did not ask for;
  - only config changes need approval.
