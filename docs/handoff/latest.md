# Handoff: every waiting patch run together as one stack; its failures fixed in the patches (2026-11-24, 01:00 to 02:30 Denver)

## 0000. The 04:49 session (2026-11-24): read this first

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **C4216 closed in a patch**, `~/mercury-runs/c4216.patch` and `.msg` (worktree
  `~/nmas-worktrees/c4216` on 012526a8, staged): every pressed `<a>`/`<button>` carrying
  `hx-get` (271: tabs, DHCP, SDN, NetBox links) busy on itself by one stylesheet rule (the
  menu row's spinner, C399), and every press that loads another page busy until the page
  replaces it (nmas_v2.js `markNavigating`, never on a download: every attachment route's
  link declares `download`, by a scan). ACTIONS.md corrected (the device menu, the panel and
  the console offer were never "none"). Red on main's stylesheet, six controls
  (`~/mercury-runs/c4216_control*.sh`). land_all.sh now ends `c4216`.
- **c4226.patch had a defect, fixed in it** (found running the 121 browser and v2-script
  files over the stack: tests/test_topology_v2.py's three drag tests red, bisected to c4226;
  the 199-file run had missed that file): its press merge took the topology's drop (a
  script's submit inside `#topo`) and kept the dragged device's `data-dx`, drawing it 108 px
  from its saved place. `pressedUnit` now needs a trusted event and work outside the unit
  (`workOutside`); two new tests, two controls. c4230.patch re-based on it (content
  unchanged). The old patches are `*.patch.before-topology`.
- **Full suite over the stack (16 patches; 12 workers, 765 s): 4 failed, 32,615 passed**
  (`~/mercury-runs/suite/landing3-012526a8.{log,xml}`): test_nmas_workers' two
  unconfined-only cases, C4090's loop (its three, as before), and test_tmp_roots, which
  fails on main too in a session without USER: **C4231, fixed as a patch**
  (`~/mercury-runs/c4231.patch`: the bound asks pytest's `get_user()`; a control bites).
  So the stack lands green but for C4090 (OPERATOR.md#c4090-records).
- **C2820 item 4 (the held rows) BUILT as a patch**, `~/mercury-runs/c2820-held.patch` and
  `.msg` (worktree `~/nmas-worktrees/c2820`): the ratchet now reads the installation's held
  decisions (new fixture `tests/fixtures/heal_records/held_decisions.jsonl`, guards 4, 6, 9;
  on main's attention.py: 3 guard numbers, 2 History lookups); `_held_said` says each in
  words, the guard in the record. Aimed 2,032 passed (C4090's loop the one red).
- land_all.sh now ends `c4216 c2820-held c4231` (18 patches); all apply; the three new
  patches' tests pass on the stack (116).
- Left in Stage 5 item 1: ACTIONS.md's "could reuse it" list (busy-and-in-place actions moved
  onto the stepper as jobs).

## 000. The 03:35 session (2026-11-24)

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **C4226's fix BUILT as a patch**, `~/mercury-runs/c4226.patch` and `.msg`, now based on
  c4229 + c4228 (the tree `~/mercury-runs/tree-c4229-c4228.txt`, a `git write-tree`, no
  commit): `pressedUnit`, `fresh` in `morph`, `loaded` (htmx:load on the drawn unit). Red
  first (4 of 5; the fifth guards the merge), three controls bite. Aimed on c4228 alone: the
  199 files reading the v2 script or serving a browser, 6,428 passed.
- **c4229.patch had a defect, fixed in it** (worktree `~/nmas-worktrees/c4229` staged, patch
  and .msg refreshed): the focused control counted as a person's work, so the update page's
  Check again kept "Still no answer" after the check answered
  (test_update_button's test_a_check_that_hangs_…, red with c4229, green on main and now).
  `holdsWork` skips `ctx.pointed`.
- **C4230 cause 6 and C4223 measured (UNKNOWN to B); cause 6 fixed as a patch**,
  `~/mercury-runs/c4230.patch` and `.msg` (worktree `~/nmas-worktrees/c4230` = c4229 + c4228 +
  c4226 + c4230, the last staged against `tree-c4226.txt`): `keptRevisited` for every kept
  part but the pointer's, `drawnAlike` so a marker never restarts a component. Red first, two
  controls bite. The pointer's keep is left out: revisited, it moved C2841's Right 80 to
  182 px (test_live_marks, the same incident held), so C4223 stays open, measured, needing
  its own design.
  Cause 5 measured: no shift in Firefox (scroll anchoring). Causes 7, 8 unmeasured.
- **The four together (c4229 + c4228 + c4226 + c4230) over the 199 files that read the v2
  script or serve a browser: 6,432 passed, 0 failed** (`~/mercury-runs/c4230-stack-aimed2.log`).
- land_all.sh's order now ends `c4229 c4228 c4226 c4230`. The scratch measurements are
  `~/mercury-runs/c4226_*.sh`, `c4230_*_measure_test.py`, `c4230_controls.sh`.
- **Next:** the plan's Stage 5 item 1 (one shared progress component) or the human-readable
  pass; everything test-changing stays a patch.

## 00. The 02:11 session (2026-11-24): the 02:30 handover only

- Started at 02:11 Denver, 19 minutes before the handover: no full suite, deploy or patch
  started (C4226's fix needs a red test first and the C4228 merge-path interaction, below).
  This file was kept as `docs/handoff/2026-11-24.md`; nothing else changed. **The next
  session (03:35) starts at section 0's Next: C4226's fix as a patch on top of c4228.patch.**
- A second session started at 02:13 Denver: still label `unconfined`, OPERATOR.md unanswered
  (session-namespace, c4090-records); the handover only again, nothing else changed.
- A third session started at 02:15 Denver: the same (label `unconfined`, no answer, origin at
  44af9da6); the handover only, nothing else changed.

## 0. The small-hours session (from 01:02 Denver, 2026-11-24): read this first

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **The landing stack:** `~/mercury-runs/land_all.sh` applies all ten patches in section 1's
  order onto a scratch worktree (`~/nmas-worktrees/landing`, made fresh on f9ec3f88 each
  time), keeping both sides in the three append-only docs (OPEN_FINDINGS, TIER_HAND_CHECK,
  STANDING_APPROVAL_LOG); write one fresh Count line after (register_count.py). Every patch
  applies; no code conflict.
- **First full suite over it** (`suite/landing-f9ec3f88.xml`, 12 workers, worksteal, 775 s):
  9 failed. Known: C4090's three loops, test_nmas_workers' two unconfined cases. **The stack's
  own six, each fixed in its patch** (worktree staged, patch and .msg refreshed):
  C3886's save-check docstring named r1 and s1 (test_device_names); the assistant's read-loop
  `ask` hid its trigger in `**k` (test_ai_triggers), `assistant_threads._masked` was in no
  masking list (test_url_userinfo_masked), assistant.py not in KNOWN_LOOP
  (test_read_loop_never_read), two masking tests asserted only their answer (test_presence_only:
  now the kept thread, two controls bite), and tab-intent, in-progress and incidents records
  stale (re-compared by diff; one log line, "The Assistant's button is drawn disabled while it
  is off").
- **C3709 closed inside the assistant patch** (the diagram from STEPS as built; manual tests 73
  passed). It is NOT in the second stack run (made before it); its own tests passed.
- **Second full suite over the corrected stack** (`suite/landing2-f9ec3f88.xml`, 780 s): **3
  failed, 32,589 passed**: test_nmas_workers' two cases (pass in a namespace) and C4090's three
  loops, now asked as OPERATOR.md#c4090-records. So once session-namespace is answered the
  patches land green but for C4090.
- **Landing, once a commit can be made:** per patch in order, `git apply --3way --index`, keep
  both sides in the three docs, a fresh Count line, the aimed tests in its .msg, commit
  (`git commit -F`, its first line checked), push; then one full suite; then deploy if C4090 is
  answered. The scratch `~/nmas-worktrees/landing` was removed at 01:55; `land_all.sh`
  rebuilds it on a fresh `git worktree add --detach` (now eleven patches, C4229's last).
- **C4228 measured, UNKNOWN to B** (01:56 session, scratch `~/mercury-runs/c4228_measure_test.py`,
  same harness): an answer a press draws inside a part of a region (the Settings group card is
  no region) is kept in all eight cases; an answer drawn by a press that swaps a REGION itself
  (e.g. _ai_classes.html, _code_repo.html cards) is captured as the server's copy and removed
  by the next merge. Surveyed (`~/mercury-runs/c4228_survey.py`): 117 of 301 presses, in 57
  templates, target a region (111) or live part (6) by id (an upper bound). **Its fix is BUILT
  as a patch**, `~/mercury-runs/c4228.patch` and `.msg` (base cc39f197; worktree
  `~/nmas-worktrees/c4228`, branch fix/c4228, staged): `markUnread`, `answersSeen`, `heldParts`
  keeps an unread answer. Keep test red on cc39f197, seen test bites under a control; aimed
  798 passed. Applies cleanly after c4229 (checked); added to land_all.sh last. At landing,
  move C4228's row to Closed.
- **C4226 measured, UNKNOWN to B** (scratch `~/mercury-runs/c4226_measure_test.py`: a real
  htmx press, its answer set on the region's own beforeSwap): a press in card B swapping the
  whole live region (outerHTML or innerHTML) drops card A's typed text, tick and open state,
  the focus in the field notwithstanding. **Next:** C4226's fix as a patch (a press's answer
  into a remembered region merged, held parts outside the pressed card kept: `mergeSpec`
  ~1125 and `holdWhileEditing` ~480 in nmas_v2.js), its test red first from the scratch shape;
  then C4230. **Watch:** once a region press merges (mergeSpec letting a non-live swap into a
  remembered region through), `captureSwapped` returns early on `nmasMerged`, so C4228's
  `markUnread` must move into that merge path too; build C4226's patch on top of c4228.patch
  and re-run TestAPressAnswerIsKeptUntilSeen. Not started (02:10 Denver, too close to 02:30). The previous handoff is
  docs/handoff/2026-11-24.md (this file at the 02:30 handover; before it, 2026-11-23.md).
- **C4227 closed as measured** (the refresh audit's cause 2): the live merge keeps a tick, a
  radio and a chosen option (Devices through a real `reachability` redraw; keyed rows merged
  directly, changed and unchanged). The scratch test is `~/mercury-runs/c4227_measure_test.py`
  (run by `nmas-control`; it reuses tests/test_live_merge.py's `_merge` and a real page). Its
  Devices case drew no row change, so C4229 was measured next with the same harness.
- **C4229 measured, UNKNOWN to B:** rows inside a `<form x-data>` (Devices' selection form)
  lose every tick, radio and option when one row's text changes (`morph`'s restart,
  static/js/nmas_v2.js ~844, replaces the component whole). **Its fix is BUILT as a patch**,
  `~/mercury-runs/c4229.patch` and `.msg` (base 933f1c08; worktree `~/nmas-worktrees/c4229`,
  branch fix/c4229, staged): `morph` merges a component in place while it holds a person's
  work (`personsIn`, new; `holdsPart`). The new test is red on 933f1c08's script, and a
  control of the select logic bites. Land it after the stage5 patch (section 1's order), and
  add `c4229` to land_all.sh's list.
- Committed only docs (a9d1108d and the commit after); nothing deployed.

## 0a. The late session (from 22:37 Denver, 2026-11-23)

- **Still blocked the same way:** AppArmor label `unconfined`, no answer in OPERATOR.md, so
  test-changing work stays patches. Every patch's code still applies on 1c6d3687; each
  conflicts only in docs/OPEN_FINDINGS.md (checked 23:00 Denver in a scratch worktree).
- **Landed (pushed):** 3e5c9b51 (C4222's History case: the `planted` fixture keeps the AI call
  record in its own folder; reproduced red then green), d5d966d1 (C4184: three scans once a
  process, each answer compared equal: readers 22.4 to 5.9 s, manual references 18.6 to 14.1 s,
  source survey 48.2 to 24.8 s), 1c6d3687 (C2974 fixed: dns_blacklist's TESTING.md item 1;
  C4225 closed, measured: the request lines land, the host had one page visit in 400 hours),
  bb7fdb14 (C4184: the v2 walk parses each template once, 58.4 to 50.0 s), b5ce81b7 (C2820:
  the bare-identifier backlog 11 to 0, History's AI-call and notification rows), b0afda01
  (C4222's last case: conftest puts the device-holds store back per module; five modules'
  children left 22 interrupted-operation rows on every later Needs attention page).
- **C4222 now waits only on C4200's patch**; after it lands, one serial run confirms the
  serial and parallel counts match (Stage 2 item 1).
- **Main's CI still red** on C3886's test_heal_act and C4090's three loops (the host's fix-it
  records re-read: the same 14 files as the 00:51 UTC capture, so no new kinds).
- **C3709** (the assistant's manual diagram) waits for the Stage 4 patch: that patch changes
  the assistant's steps (`place` first) but not `manual_diagrams.assistant`, so the diagram is
  redrawn from the steps after it lands.
- **Measured (Stage 2):** b0afda01 with the render-cache and C4200 patches, `-n 12 --dist
  worksteal` (CI's scheduler): **774 s wall**, 7,738 s summed (`suite/ws12-b0afda01.xml`); the
  default scheduler on d5d966d1 gave 832 s. So once the patches land about 175 s remain over
  10 minutes; the tail is the longest single tests (the v2 walk 70 s, the source survey's
  population 56 s, the swap clicks 50 s) and collection (27 s a process). A 12-worker run
  needs `NMAS_TEST_TIMEOUT=1470` (the 300 s default stopped the first one).
- **Next:** land the patches (latest's section 1 order) once session-namespace is answered;
  then Stage 2's tail (split the walk's long single tests?) and Stage 6's rows.

## 0b. The night session (from 20:03 Denver, 2026-11-23)

- **Still blocked:** this session too has AppArmor label `unconfined` (no namespace), so every
  test-changing commit stays a patch (OPERATOR.md#session-namespace).
- **CI on main is red** on three tests (every run since before d24cbdc4): C3886's
  test_heal_act (fixed in `c3886-keyed-placeholder.patch`), C4090's three loops in
  test_v2_context_is_drawn (need captured records, or the operator's words for
  EMPTY_IN_FIXTURE), and test_no_utc_drawn (b0c9b952's captured records): **the last fixed,
  c6ca9163.**
- **The assistant's hand check: DONE** in its worktree, the patch refreshed
  (`stage4-assistant.patch`, 33 tests): 20 mutants all died by run 2, 7 new tests.
- **C4200 found and fixed as a patch** (`~/mercury-runs/c4200.patch`, `.msg`; worktree
  `~/nmas-worktrees/c4200-fix`, branch fix/c4200): the test before the one the probe named,
  `test_the_tag_survives_the_declarations_expiry`, ran `decide.run` in AUTO outside
  `acts_with`, so a real heal job outlived it and wrote a needs-a-person step into the
  session's store. **Its serial full run (85 min, 20:55 to 22:20 Denver): 25 failed to 7;**
  19 of C4222's 21 serial-only failures pass. Left serial-only: test_history_one_timeline (1)
  and test_no_control_moves's Needs attention row (1): C4222's next step. The patch's message
  carries the measurement.
- **Stage 5's refresh audit DONE** (9f905ced, `design/review/REFRESH_AUDIT.md`): C4226 to
  C4230, each UNKNOWN with its measurement; the fixes change tests/test_live_merge.py.
- **Last measured full suite:** serial 5,092 s (the C4200 run); 12 workers on 9f905ced 949 s
  (`suite/main12-9f905ced.xml`, 14 failed: main's two reds, test_nmas_workers' two
  unconfined cases, and C4200's victims, test_one_cause_one_row 9 and test_no_control_moves
  1). The cut files 707 s to 263 s summed; the rest ran 15% slower that run (machine load).
- **Stage 2 (C4184), landed:** 7ef8673e (AI route scans once per text, 216 s summed to ~14 s),
  a4e32125 (source index survey), 7ea5a823 (the v2 walk shared across xdist workers; C1763's
  app log read from the store), 8c307c32 (writer-site scan once a process). Measured: 8,263 s
  summed in the 12-worker run, so ~1,800 s must go for 10 minutes (C4184's row).
- **Render's compiled-code cache: a patch** (`~/mercury-runs/render-cache.patch`, `.msg`;
  worktree `~/nmas-worktrees/render-cache`, branch speed/render-cache, staged; base
  6f18deea). Its first device-write review found a HIGH (a constant secret folded into kept
  code), fixed with `pass_context` and a test; the second review says SAFE
  (`~/Documents/nmas-reports/review-devicewrite-2026-11-24-render-cache-r2.md`). It changes
  a test, so it lands with the other patches. Deploy files about half the time.
- **Stage 6, first ranking** (`~/mercury-runs/page_times.py`, the walk's fixture lab, warm,
  in-process): 2,024 requests in 22 s; slowest GET /v2/device/<d>/deploy (0.10 s mean, 0.38
  worst), POST /v2/sdn/dhcp/confirm and /v2/sdn/flow/confirm (1.5 s once each), intent
  words and check posts (0.25 to 0.7 s). Nothing over a second on a page GET; real host times
  are the next measurement.

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
- The assistant patch's hand check (data to the model) is NOT done: an agent started it in
  `~/nmas-worktrees/assistant` at about 18:45 Denver and had written no entry when this session
  ended (20:05). Check that worktree's `git status` and docs/TIER_HAND_CHECK.md; redo it if no
  entry "2026-11-24: the toolbar assistant's stage 2" is there, then refresh the patch.
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

- main is f9ec3f88 plus this session's handoff commit (pushed). Nothing deployed. Main's CI
  red as before (#2030: C3886's test_heal_act, C4090's loops). Full suites this session: two
  over the landing stack, 12 workers (775 s and 780 s).
