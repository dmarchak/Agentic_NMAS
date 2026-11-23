# Fast lane: deploying ahead of the tests (a reusable mode, off by default)

**What it is.** A temporary working mode the operator turns on when the full gate (about an
hour a change) would block live work, such as a supervised lab window or a rehearsal. It was
first used from 2026-11-15 to 2026-11-17, for the Lab 10 crunch (the operator's decisions of
2026-11-15 and 2026-11-16, quoted at the top of docs/FAST_LANE_DEBT.md), and retired on
2026-11-18 (the operator: "Turn fastlane off and restore full CI gating"). It is **off by
default**: `scripts/nmas-deploy --fast-lane` is refused while it is off, naming why.

It has two levels:

| Level | What still runs | What is skipped |
|---|---|---|
| **Fast lane** | the commit hooks; the touched files' own tests before the deploy; the nightly backup window; the smoke check after the restart, with its automatic rollback; full CI on every push to main (after the deploy, not before it) | the gate's full suite before the deploy, and the gate's or CI's verdict the deploy bar asks for |
| **Skip mode** (inside the fast lane) | the commit hooks; the backup window; the smoke check and its rollback; an independent review of code that writes to devices | every test run, every new test, red-green proofs, boards, fidelity records, manual updates |

`nmas-deploy` runs no preflight in either level. Its smoke check is `nmas-post-deploy-check`
without C3133's `--expect-local-account-off`, so a deploy is never refused for the local
account being on (C4075, the operator's ruling 8 of 2026-11-18: the words match the code, and
the flag is a registered build).

**Why it exists.** With the operator at the keyboard, a change can be needed live in minutes,
not after an hour of gate. The smoke check and the automatic rollback bound a bad deploy's
harm, and CI keeps measuring what the change broke.

**A release that is not ready is never rolled back automatically** (the operator's ruling 2,
2026-11-18, keeping 973952c5, C4006). A fast-lane release that is not confirmed running,
whose units are not confirmed, or that is not ready returns before the smoke block. The smoke
check and its automatic revert did not run, so the deploy's verdict says so in so many words,
and gives the revert to run by hand (`nmas-deploy --revert`). Only a smoke check that ran and
went red puts the previous release back by itself.

## The risks it carries (measured on its first use)

- **CI goes red and stays red, so its red stops meaning anything.** From the first fast-lane
  commit (3d3a829, CI run #1748, 2026-11-16) to the last (55a3c6b, #1821, 2026-11-17), every CI
  run on main failed: 71 commits. A new break looks like the old ones.
- **Test premises drift.** Each decision that changed behaviour (holds removed from the heal
  path, Save as the approval, every AI request streamed, Mercury's own AI limits removed) left
  its tests asserting the old behaviour. One changed seam (a stub's signature) made about 250
  heal tests read "held" for a reason unrelated to what each test checks.
- **Real defects hide among the expected failures.** In #1817 (the last full run, 1,243 failed
  and 41 errors) were a device read sent outside its one home (`pipeline._read_like_before`) and
  findings of the scans that exist to refuse such things; a red that is "expected" is read by
  no one.
- **The debt compounds.** Each shipped change adds a row of owed tests to
  docs/FAST_LANE_DEBT.md; the plan of 2026-11-16 sized 28 rows at about 76 agent-hours, and the
  list kept growing after it.

## Turning it on

1. The operator decides it, in words, with a scope and an end (a date, or a named event).
2. On the machine that runs `nmas-deploy`, write the mode file, `~/.config/nmas/fast-lane.json`
   (or the path in `NMAS_FAST_LANE_FILE`), owner-only:

   ```json
   {"by": "<operator>", "at": "2026-11-15T20:00:00Z", "until": "2026-11-17T23:59:00Z",
    "why": "the Lab 10 supervised window"}
   ```

   `nmas-deploy` reads it on every `--fast-lane` deploy (`fast_lane_mode`): absent, unreadable,
   missing a key, or past its `until`, the lane is off and the deploy is refused before anything
   moves. Each fast-lane deploy's record (data/deploy_audit.jsonl) carries the mode's words.
3. Add a row to docs/FAST_LANE_DEBT.md for every change shipped while it is on: what it skipped,
   and which tests, boards and reviews it owes.

## Turning it off

1. Delete the mode file (or let its `until` pass): `--fast-lane` is refused again, naming this
   page. `--revert` (back to the previous deployed release) works either way: it is recovery.
2. Run the catch-up below before the next ordinary deploy (`nmas-deploy --wait`).

The release that made the mode off by default (40fb2926) changed `scripts/nmas-deploy`, which the
host keeps twice: the checkout's copy and the updater's root-owned copy. After deploying it, run
once from the host's checkout `sudo install -o root -g root -m 0644 scripts/nmas-deploy
/usr/local/lib/nmas-update/nmas-deploy`, then `scripts/nmas-update-check` (docs/UPDATE.md,
"Re-install").

## The catch-up (mandatory when it ends)

What the first catch-up did (overnight 2026-11-17 to 11-18), in order:

1. **Inventory:** the first fast-lane commit, the last green CI run before it (#1747, f195b03),
   every commit merged to main while it was on (`git log <last green>..origin/main`), the debt
   list, and whether any ratchet moved (`git diff <last green> origin/main --` the coverage
   baseline, tests/ratchet_lists.py, tests/skip_reasons.py, tests/publication_exemptions.py, the
   workflow and the gate's scripts; and `Test-Weakened:` trailers in the range). The first time:
   none moved.
2. **Every suite on main's head, as the gate runs it** (`scripts/nmas-gate`'s step 4: the five
   shards, CI's interpreter and workers, confined, coverage by tier, JUnit per shard), in a clean
   worktree outside the checkout, so every failure is named. CI's own logs truncate.
3. **Cluster the failures by cause**: a changed seam a test stub does not take, a premise a
   decision changed, a real defect. Fix one cause per commit, with the test that shows it (the
   commit hooks' red-green and bypass checks still apply; a premise correction names the decision
   that changed it). A cause that needs the operator's decision is recorded and left.
4. **The ratchets** (the coverage baseline, the skip and exemption lists) back at their
   pre-fast-lane values or stricter; never looser.
5. **The full gate and CI green on the final sha** before the next ordinary deploy.
