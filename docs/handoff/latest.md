# Handoff: Stage 3 done; Stage 1's test changes built as patches, waiting on the operator (2026-11-23, evening)

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

**Test-changing work is kept as patches in `~/mercury-runs/`**, each with its commit message
(`.msg`), made with `git diff --cached --binary` on main at a287651e. Once a commit can be made:
`git apply --3way --index <patch>` on main, resolve docs/OPEN_FINDINGS.md (both patches and later
commits add a Count line and Closed rows at the same places: keep every row, write one fresh Count
line by `~/mercury-runs/register_count.py`, run from the checkout), run the aimed tests named in the message, commit with
`git commit -F <msg>` (check its first line), push.
- `c3886-keyed-placeholder.patch`: C3886 (the operator's keyed-fingerprint ruling), its
  device-write review done (`~/Documents/nmas-reports/review-devicewrite-2026-11-24-c3886.md`:
  safe, its MEDIUM 2 and LOWs 1 to 4 and 7 answered in the patch; MEDIUM 1 is C4210). Hand check
  in the patch (14 of 14 mutants died). Worktree `~/nmas-worktrees/c3886` (branch
  rulings/c3886-keyed, staged). `~/nmas-worktrees/rulings-gui-kit` holds an older staged copy:
  ignore it.
- `c4207-c4208.patch` (base a287651e): C4207 and C4208 (the operator's rulings). Its first
  device-write review said not safe (H1, M1, M2, L1: review-devicewrite-2026-11-24-c4207-c4208.md);
  each fixed and tested in the patch; C4217 registered (L3). Its second review, with C4205's, was
  started at about 17:50 Denver: `review-devicewrite-2026-11-24-c4207-c4208-r2-c4205.md`.
  Worktree `~/nmas-worktrees/c4207` (branch rulings/c4207-c4208, staged).
- `c4205-runs-on.patch` (base b0e450c2): C4205, Save's "runs on" line follows the ticks and
  Dry run. Reviewed with C4207's second review. Worktree `~/nmas-worktrees/c4205`.
- `c4090-reader.patch` (base b0e450c2): `nmas-config-read --records`, its test, C4218. Worktree
  `~/nmas-worktrees/c4090`. The records it captured from the host's Default network (masked) are
  in `~/mercury-runs/c4090-capture/` (2026-11-24 00:51 UTC); an agent was building C4090's
  fixtures and providers from them in the main checkout (tests/v2_context.py and a new
  tests/fixtures folder, staged, not committed): that part changes no test function, so it can
  be committed here once its checks pass.
  C4090's fixtures and providers landed (b0c9b952): seven of ten loops.
- `c4195-c4196.patch` (base b0e450c2): the SDN scan-reply problems; red-green checked by hand
  (5 selected, 5 red); its device-write review was started at about 18:25 Denver:
  `review-devicewrite-2026-11-24-c4195-c4196.md`. Worktree `~/nmas-worktrees/c4195`.
- C4207-C4208 and C4205 had their second review: both safe
  (`review-devicewrite-2026-11-24-c4207-c4208-r2-c4205.md`); its N1, N2 and N4 fixed in the
  patches, N3 in the decisions file.
- C4081 DONE (ccbdeceb): the press's own invalidation redrew the page over its focused answer;
  the live merge now keeps a focused answer (static/js only).
- C4195-C4196 revised after its review (the HIGH and both MEDIUMs fixed, C4221 registered in the
  patch); its second review was started at about 19:00 Denver:
  `review-devicewrite-2026-11-24-c4195-c4196-r2.md`.
- The assistant patch's hand check (data to the model) was being done by an agent in
  `~/nmas-worktrees/assistant`, writing into that worktree's docs/TIER_HAND_CHECK.md and
  refreshing the patch.
- `stage4-assistant.patch` (base b0e450c2; applies on 64ed46b2): Stage 4, the assistant to
  `docs/design/assistant.md`; 26 tests, the model mocked, 21 controls shown failing. Owed
  before its deploy: the irreversible tier's hand check (new data to the model,
  docs/TIER_HAND_CHECK.md). Its decisions are in the decisions file. Worktree
  `~/nmas-worktrees/assistant`.
- C4195-C4196's review said not safe (a HIGH: a scan's only replying host taken as a mirror and
  rate-limited in AUTO; two MEDIUMs); its builder was fixing them in the same patch.
- C4195-C4196: reviewed three times, the third safe (`...-c4195-c4196-r3.md`); its under-
  responses are C4224 (on main).
- `stage5-settings-descriptions.patch` (on 17e86d7c): every Settings screen's setting shows its
  one line from `settings_schema.DESCRIPTIONS`; run the publication denylist test in the
  checkout before committing it (the worktree lacks the local files). Worktree
  `~/nmas-worktrees/settings-desc`.
- Land them in this order (then the assistant and the settings descriptions): C3886, C4207-C4208, C4205, C4090's reader, C4195-C4196 (after its
  review), C4081, then a full suite.

## 2. Where the plan stands

- **Stage 1:** C4206 DONE (c591f1c6). C3886, C4207 and C4208 built as patches (above). C4090,
  C4205, C4081, C4200, C4195 and C4196 not started: each changes a test (BLOCKED).
- **Stage 2:** the serial run finished (6,522 s): 25 failed, 21 of them only serially (C4222,
  `~/mercury-runs/suite/serial-vs-m.txt`). C4200's whole-suite probe runs detached from 19:04
  Denver in `~/nmas-worktrees/c4200-probe` (b0e450c2), about 110 minutes: the first line of
  `~/mercury-runs/c4200-full.jsonl` with rows names the test that leaves an incident behind:
  **found at 19:56: `tests/test_fault_drills.py::TestTheTag::test_a_tag_that_cannot_be_read_is_real`**
  (C4200's row). Next: find where its incident is written outside its `lab` store and fix it
  there; then compare the probe's JUnit (`suite/c4200-serial.xml`) with `serial.xml`, and
  remove the worktree once the probe ends (about 20:55). Fixes that change tests: BLOCKED.
- **Stage 3: DONE** (fd9e6e77, a287651e, 15da95a2, 401dc9a4). The operator is asked to pick a
  direction (OPERATOR.md#gui-direction); Stage 5's after-pick items wait on it.
- **Stage 4 next:** the assistant (`docs/design/assistant.md`); code and tests, so built as a
  patch until session-namespace is answered.

## 3. State

- main is cd2e3c7a (pushed). Nothing deployed. Full suites this session: the serial run (done)
  and C4200's probe (running).
