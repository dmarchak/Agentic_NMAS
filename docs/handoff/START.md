# The standing prompt for every automatic session

This file is the prompt `tools/nightly/mercury-session.sh` gives each automatic session (03:35
America/Denver, the operator's user crontab). It is public: no names, addresses or hosts.

You are continuing an unattended run on this repository. Nobody is watching: do not stop to
ask. Where a choice is the operator's to make, take the most reasonable option, record it in
the day's decisions file (`docs/handoff/decisions-<yyyy-mm-dd>.md`, one line each: decision |
why | how to reverse) and carry on.

## Start

1. Read `CLAUDE.md` and `docs/handoff/latest.md` only. Do not scan the whole repository.
2. Carry on with the plan in `latest.md` from where it stopped (its "Next" section names the
   step). Do not re-do a finished step and do not re-read files a previous session summarised.
3. If nothing left in the plan can move without the operator, write the daily report and exit.
   Do not invent new work.

## Run rules

- Work in the plan's phases, in order. After each phase: commit; update `latest.md` so a fresh
  session could pick up from that point; keep the context small.
- If you run low on context, finish the phase you are in, update the handoff and stop.
- Tests are never weakened, skipped or deleted. Run one full suite at the end of each phase.
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

- No deploy unless `latest.md`'s plan names one. Leave main ready; the operator deploys.
- Where a deploy is planned: only through `nmas-deploy`, never between 02:30 and 03:30
  America/Denver, and never start one after 02:00.

## The 02:30 handover

- Check the time with `TZ=America/Denver date` before starting a phase, a full suite or a deploy.
- Do not start a full suite after 02:00 unless it will finish by 02:30 (the last measured
  full-suite time is in `latest.md`).
- At 02:30, stop at the next clean point: never mid-deploy, mid-merge or mid-commit. Revert any
  half-done uncommitted edits. Then commit, rewrite `latest.md` (keeping the previous one as
  `docs/handoff/<yyyy-mm-dd>.md`), write the daily report and exit. The next session starts at
  03:35.

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
