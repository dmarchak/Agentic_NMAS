# Decisions, 2026-11-24 (Denver)

One line each: decision | why | how to reverse.

- Every waiting patch applied together in a scratch worktree (`~/nmas-worktrees/landing`, on f9ec3f88, in latest.md section 1's order, register and hand-check log conflicts resolved by keeping both sides) and one full suite run over the stack, rather than waiting idle on session-namespace | it says now whether the stack lands green, so the session that can commit spends its time committing, not debugging | none: nothing committed; remove the worktree.
- No cut to the console fakes' quiet window (`FAST.quiet_s`, 0.3 s, about 2.2 s of each console case's 2.3 s) | profiled at about 75 s summed and 6 s wall for a halving, against a flake risk under 12 workers | none.
