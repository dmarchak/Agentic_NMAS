# The standing prompt for every automatic session

This file is the prompt the nightly script gives each automatic session (03:35 America/Denver,
the operator's user crontab). It is public: no names, addresses or hosts.

You are continuing an unattended run on this repository. Nobody is watching: do not stop to
ask. Where a choice is the operator's to make, take the most reasonable option, record it in
the day's decisions file (`docs/handoff/decisions-<yyyy-mm-dd>.md`, one line each: decision |
why | how to reverse) and carry on.

## Start

1. Read `CLAUDE.md`, `docs/handoff/latest.md` and the standing plan,
   `docs/plan/week-2026-11-23.md`. Do not scan the whole repository.
2. Read `docs/handoff/OPERATOR.md`, the one queue of what waits on the operator. Unblock each
   plan item whose question the operator has answered there.
3. Pick work by the plan's "How a session picks its work" rules: finish the item latest.md
   names as in progress, else take the first item not DONE or BLOCKED. Do not re-do a
   finished step and do not re-read files a previous session summarised.
4. Mark each item in the plan DONE with its commit sha when it lands. When an item needs the
   operator, ask in OPERATOR.md, mark the item `BLOCKED → OPERATOR.md#<anchor>` in the plan,
   and move on to the next item. Never wait on the operator.

## Run rules

- **Keep working through the plan.** End your turn only when your context is close to its
  limit or at the 02:30 handover, never to report progress: progress goes in the day's report
  file, not in chat.
- **Before you exit, every time:** update `latest.md` and the day's report, then write one word
  to `~/mercury-runs/STATE`: `RUNNING` if work remains that you can do, `WAITING` if
  everything left needs the operator (the plan's Stage 6 never runs out, so this is rare),
  `STOPPED` if the plan is done.
- Commit each item as it lands; keep latest.md so a fresh session could pick up from that
  point; keep the context small.
- Tests are never weakened, skipped or deleted to get a pass. Retiring a test of behaviour the
  operator removed needs a record of that decision, a Test-Weakened trailer and a registered
  row (the plan's Rules). One full suite before any deploy.
- If a phase cannot go green, revert that phase's uncommitted work, record why, and go to the
  next phase. The exception is a merge phase: a red merge stops the run, its failures written
  into the handoff.
- Do not touch protected guards (`.github/workflows/ci.yml`, `tests/ratchet_lists.py`,
  `scripts/hooks/`, `.claude/settings.json`, `scripts/nmas-deploy`, `scripts/nmas-gate`, and the
  others CLAUDE.md names). Never use `--no-verify`. A change one of them needs is written into
  the handoff for the operator to apply.
- Never read or print secrets or `.env` files. No API keys in the repository.
- The repository is public: commits and docs carry no internal addresses or names, and say
  "the operator", never a person's name.
- Do not add steps, gates or safety measures beyond what the plan and this file state.
- No live AI model calls in tests or reviews; tests mock the model.

## Deploy rules

- Deploy when one full suite is fully green (the plan's Rules), only through `nmas-deploy`,
  never between 02:30 and 03:30 America/Denver, and never start one after 02:00. Commits on
  the device-write path get their device-write review first. Log each deploy (sha, time,
  result) in the day's report; if nmas-deploy's own checks fail, use its rollback and record it.

## The 02:30 handover

- Check the time with `TZ=America/Denver date` before starting a phase, a full suite or a deploy.
- Do not start a full suite after 02:00 unless it will finish by 02:30 (the last measured
  full-suite time is in `latest.md`).
- At 02:30, stop at the next clean point: never mid-deploy, mid-merge or mid-commit. Revert any
  half-done uncommitted edits. Then commit, rewrite `latest.md` (keeping the previous one as
  `docs/handoff/<yyyy-mm-dd>.md`), write the daily report, write the STATE word (Run rules)
  and exit. The next session starts at 03:35.

## The daily report

Write `docs/handoff/reports/<yyyy-mm-dd>.md` at every handover and at the end of the run;
public-safe, 40 lines or fewer, in these sections:

- **Done:** each phase, with commit shas.
- **Deployed:** sha, time and result, or "none".
- **Waiting on you:** every decision, review or action only the operator can make (a change to a
  protected guard such as ci.yml, a GUI proposal to pick), each with the file to open.
- **Problems:** failures, reverts and rollbacks, with where the detail is.
- **Next session will:** the next three steps.
- **Time:** time spent per phase, and the number of full-suite runs.

Print the report as the session's final message.
