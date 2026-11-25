# Handoff: main red only on C4090; nothing deployed (2026-11-25, 02:30 Denver)

## 0000000000000000. The night of 2026-11-24 to 25 (17:05 to 02:30 Denver): read this first

- **State.** Main's head is b6688704 plus this handoff's commit (the last code commit is
  78a0599f; those after it are docs and the register). CI on every push from cdd4e46c to
  c46eaf6f, the last read at 08:57 UTC, is red on C4090's loop test alone. Its three loops,
  `_fixit_section.html` F.more and `_inc_proof.html` P.net_zero.lines and P.reads, wait on
  records only the operator can make (OPERATOR.md#c4090-records). Nothing was deployed: there
  has been no fully green CI. The full local suite at c46eaf6f is the same: see the last
  bullets.
- **What landed.** Every item, with its sha, is in docs/handoff/reports/2026-11-24.md, under
  Done. Since 23:40 Denver:
  - C3601 closed: every page job is listed by In progress and reopens.
  - C4260: job ids in page links are shape-checked.
  - C4253.
  - Save, Promote and Set Automatic are bound to what their card drew (C4057, C4050, C4261);
    the retry runs only on the incidents named (`retry.run`'s `only`). Each was reviewed
    independently before any deploy.
  - C2528: EOS, AOS-CX and ProCurve credential lines are masked by position, its tier hand
    check logged.
  - Measured and closed: C4041, C3983, C3986, C4040, C3409. Measured and re-sorted: C4037 and
    C4106 to B, C4048 to C.
  - C3852: a pooled read needs the same named account (a defence: not reachable through
    today's callers, reviewed) (dbeaed3f).
  - C3884: a heal that could not be confirmed still needs proof after a re-decision. It has
    its own flag, `unconfirmed`, and one test, `incidents.needs_proof`, read by the seven
    proof readers. Reviewed; its commit is the night's last code commit.
  - C3977 narrowed:
    - its cap case already held;
    - Gate 2's limits guard given back its test, shown red with the guard off (4d623a2e);
    - the cap's refusals name the next call's cost, not a worst case, with a canary
      (c8feebef);
    - a failed AI start leads its incident's Incidents row (e1d65f16);
    - In progress names a run's declared step mid-apply (8ea80209). The same commit fixed a
      red I caused: tests/test_job_stepper.py's scan depended on the folder's order, and
      94443c71 made it fail in this checkout's order.
  - C2611 narrowed (abaf4b45).
  - C3977's last part (`record` drawn skipped before it ran) is not reproduced from the
    declared steps: mid-run, the plan engine's and a command plan's `record` draw waiting
    (measured 08:27 UTC, on the row). The fix-it agent's own run record would settle it.
- **Register:** 2,030 open (A 9, B 452, UNKNOWN 283, C 1,286), counted at 09:00 UTC (C3778
  closed and C3739 measured at the stop, b6688704). Open A
  and B rows blocking Phase 8: 56, under rule 4's cap of 60 (3 of them tagged Lab 9 or Lab 10:
  blocks), counted 08:27 UTC.
- **Waiting on the operator (OPERATOR.md):**
  - c4090-records and c4090-confirms: the last red.
  - c4075-smoke (new): should `--wait` deploys run the smoke check with the local-account
    flag?
  - claude-md-0230, gui-direction, ci-shards-gate, c2518-runner, c4135-age.
- **Lessons** (decisions-2026-11-24.md, the last eight entries):
  - Read a standing red by its list, not its name.
  - Run the presence scan for any test that reads a page.
  - A review of a new link pattern asks what else uses it.
  - Measure with the caller's own input.
  - A close note is one paragraph.
  - The aimed set for a page's new query field includes tests/test_ai_typed_text.py (the
    cdd4e46c red).
  - A fix's shape copied to a neighbour needs its premise checked there (C4261's own incident).
- **Next session:** C4090's records first (the operator's 13:15 order). Then CI's 10 shards,
  then Stage 5's direction-independent items, each deployed on a fully green CI.
- **Rows read tonight and left, each for a reason:**
  - C3884 was built at the end, not left: see What landed. Its review's three low items are
    C4263 (C).
  - C3911: a moved switch-on line's batch words and guard 8's grace. C3909 keeps "the
    problems open at the press" by design, so the change is to recording and grace, inside
    the batch.
  - C2490: a late can't-fix notice can start AI analysis calls, a cost decision.
  - C4262: the card's per-line reads, to be measured on the host.
  - C2717 and C3002: each needs a vocabulary or wording choice first.
  - The Lab 9 apps' A rows (C3925, C3929, C3936, C3938): their corrected copies are outside
    the repository, and Lab 9 work waits for the operator's go.
- **The full suite at c46eaf6f**, the night's last code included (local, six workers,
  confined, started 08:39 UTC): **1 failed (C4090's loop test), 32,211 passed, 432 skipped in
  695 s.**
- **The full suite at dbeaed3f** (local, six workers, confined, `NMAS_TEST_TIMEOUT=1500`,
  started 07:58 UTC): **1 failed, 32,207 passed, 432 skipped in 700 s.** The one failure is
  C4090's loop test (its three loops); the browser tests skip confined, and CI runs them. The
  first run, at 788388cb, was stopped by the default
  300 s whole-run bound at 34%, with no failure in the 11,290 tests that had finished.

## 000000000000000. The evening of 2026-11-24 (15:45 to 17:05 Denver)

- **Landed (each pushed, CI running):** C3157 a run reopened by its record (bd03b81d); C4034
  the summary's one duration (c3c54925); C4033 the strip's open count (f66333ff); C3489 the halt
  card's link (4ced67a8); C4032 Fixes' condition words (167650fa); C3505 the analysis's score
  in words (ca752e6f); C3506 the removal refusals in words, measured on the host first (no
  stored decision held the probe command; efd41a92, C4248 C); C3550 the kinds toggle's preview
  (f04946ff); C3093 a held device's proposal card (c2c0cc00); C3716 Persist's bottom line
  first (2a156cc8); C3464 the AI refusals' amounts through `money.exact_usd`, its tier hand
  check logged (a6687f9a: the canary and 11 of 21 died, 10 words-only survivors are C4249 C);
  C4247 the amounts outside the AI modules (d8e21ab6); C3485 History › Export's days in the
  viewer's zone (47660ae6).
- **Fixed forward (CI reds I caused):** two draw-only tests (7ff73264), C3506's words in four
  more tests, a device name in a comment, and a scratch path holding the home folder's name in
  this file since 24946278 (fe2c0867), Persist's details' keep key (4592f81f). Lessons in the
  decisions file: the presence, device-name and publication scans go in every aimed set that
  touches UI or product text; for a change of words, grep every test for each old phrase.
- **The full suite at 21b5766c** (local, six workers, confined, 17:30 Denver): 1 failed (C4090's
  loop test alone), 32,100 passed, 425 skipped (the browser tests skip confined; CI runs them).
  Two earlier local suites found the reds since fixed forward (a3cbe893, 72cfe886, 21b5766c).
  Main still waits on C4090 alone for its deploy. Since: C3714 (8219d709), C3713 (d7433e78),
  C3416 (fa18bbfa), C3581 and C3723 closed as measured (77478119, 3f43e9ad).
- **Since 18:00 Denver:** C2851's decision half (dd27d674: History redraws on a decision; the
  mark's half waits, measured: its own redraw takes the press's answer, the same root as C2405);
  C2735, C2762, C4086, C3121, C3494, C3988, C3963 closed as measured or overtaken; C3480 Who is
  told's answer below its Save (251b870a); C2878 the reach runbook's read words name its ends
  (d713c298); C3087's card half (7f3fd20e); C4035 narrowed (b5841ec7: the canvas folder its
  shot needs is not on this laptop). Waiting on design or a browser: C3703 (htmx disables the
  submitter first), C3482 with C3545 (the "…" modal), C3856 (a signed card's structure),
  C3002 (the operator's wording), C2696 (BGP captures, C2414).
- **Since 18:30 Denver:** C3651 (2b6bfcaa), C3982 (d855813a), C2461 (dc1518d1), C2393 a
  stopped detect pass is a job-health row (b3b866f2); C2371 and C2377 closed as overtaken (the
  heal and notify are built); three pins fixed forward (f1507630). Full suite at f1507630: only
  C4090's test. C2796 waits (its fix touches guard 13e's planned spans; review owed); C2490 is
  a policy choice (email a late can't-fix, or record it not sent); C3884 and C2774 sit on the
  heal's decide path and NetBox writes. Register: 2,087 open, B 500.
- **The scan set** for every UI or wording change: `~/mercury-runs/ui_scan_set.txt` (the
  manual, fidelity, presence, device-name, publication, walk, details-keep and other scans).
- **Next rows:** C3087 (a read's stored answer linked from History), C3713 and C3714 (the device
  page's two answers to one question), C4223's design, C4248 and C4249 (C, recorded).

## 00000000000000. The afternoon of 2026-11-24 (14:00 to 14:55 Denver)

- **Work until 02:30 Denver** (the operator, 13:25): never end a turn before 02:30, never stop
  to report, summarise or ask; progress in the day's report; questions in OPERATOR.md with the
  item BLOCKED. START.md and the week plan say so; the CLAUDE.md line waits as paste-ready text
  in OPERATOR.md#claude-md-0230. Never ask in a dialog (memory: no-dialog-questions).
- **Blocked, each in OPERATOR.md:** c4090-confirms (C4090's records need two confirms only a
  verified person gives; a walk sheet offered), ci-shards-gate (the gate's shard constants are
  a protected guard the 10-shard words do not name), c2518-runner (scripts/nmas-local-ci is a
  guard path; the patch is `~/mercury-runs/c2518-runner.patch`), claude-md-0230.
- **Landed:** Stage 2 DONE (587 s at 10 workers; serial and parallel agree, C4222 closed,
  cf819581). Stage 5: the audit's cause 7 (a chart's unchanged poll keeps its zoom, 6438b246),
  cause 8 measured not a defect (1bad9c09), self-healing's "departed" in "differs" words
  (f8080e46, reviewed SAFE; the manual's four are C4243). Stage 6, C3601: Show commands' and
  Ask the device's runs (1719cad2) and the logging path's test (c3da65e8) listed by In progress.
  A rows: C3862, C3863, C4109, C4110 closed as measured (fixed earlier, tests pass today);
  C4111 fixed (bad5a051, reviewed SAFE; C4244 B from it); C3864 closed with its missing test
  (82c212e2); C3880's page half (4e60db80). Main is red only on C4090 (CI #2102 on fad30e81).
- **A rows left:** C3424 waits on the operator's scan (fix 3); C2239, C139, C551 and the Lab 9
  Ryu rows (C3925, C3929, C3936, C3938) need device measurement or hardware; C3601's last
  callers (adopt, the golden capture batch, an app's deploy) each need a page to host its job
  (adopt's form is a dialog fragment); C3902's fuller version is "after the demo".
- **Since 14:55:** C4244 (7511a554); the landing's union merge corrected, C4226, C4228, C4230
  closed (902954d8: a union keeps a line one side deleted; resolve the register by the
  patch's side next time); C4184 closed (11fd8d43); C4235 Go on once (f3cdf251) and C4245 the
  rollout's Continue once (e1569b25, 5c9e2d77), both reviewed SAFE; C4210 the save check's own
  4 MiB cap (df96a07c); C4212 not a defect, folded into C4213, C4213 measured to C (e1c59b3b,
  e7e0e31d); C3103's two hidden tests run (c4c20c8b; the same shape found nowhere else);
  OPERATOR.md#c4135-age asked.
- **Next:** C4223's design (the pointer's keep: go down to the control once the pointer left,
  without redrawing the opened record; a browser investigation of why Right moved); C3464
  (amounts in the AI gateway's refusals through `money.usd`: about 30 lines, the irreversible
  tier's hand check owed); then B rows by user impact.

## 0000000000000. The operator's decisions of 2026-11-24, 13:15 Denver

They supersede the 11:50 deploy order below (decisions file, 13:15 lines, the words verbatim).
- **No fast lane: it is retired. No deploy until CI is fully green.** CI #2102 on fad30e81 is
  red only on C4090's loop test (coverage and every other job green): main's code is ready.
- **1. C4090's records:** make them on the sandbox device through Mercury (outside 02:30-03:30
  Denver, never on s3): main's current code if it can run against the sandbox, otherwise the
  deployed version, checking the records' shape matches what main's loops write today (the
  three loops: `_fixit_section.html` `(F.more or ())` two saved fixes matching one incident;
  `_inc_proof.html` `P.net_zero.lines` and `P.reads`, a Fixed command-plan run with a net-zero
  difference and its reads; C4090's row). Capture them masked (`nmas-config-read --records`,
  2ab64859), add the providers in tests/v2_context.py from them, C4090 green, then
  `nmas-deploy --wait` on a fully green CI. This touches devices: a planned-restart window
  only if a restart is involved; nothing staged on s3.
- **2. CI shards** (authorised in the operator's words, decisions file): ci.yml's test matrix
  and scripts/nmas-shards to 10 shards, each runner at the worker count a 4-core hosted runner
  supports; no other ci.yml change; show the pass/fail/skip counts equal before and after.
  ci.yml is a protected guard: quote the words in the commit's `Approved-By:`.
- **Never ask in a dialog:** a question goes in OPERATOR.md, the item BLOCKED, then the next item.
- Then, as before: Stage 5's direction-independent items (each deployed when green), Stage 6.
  Stage 2 is DONE (587 s at 10 workers; serial and parallel agree, C4222 closed, cf819581).

## 000000000000. The operator's decisions of 2026-11-24, 11:50 Denver (superseded at 13:15)

- **The order:** (1) deploy, C4090 the only allowed failure (decisions file, 11:50 line, the
  operator's words); (2) then make C4090's records on the sandbox device through Mercury on the
  deployed version (outside 02:30-03:30 Denver, never on s3), capture them masked
  (`nmas-config-read --records`), and make C4090 green; (3) Stage 2's serial vs parallel
  counts; (4) Stage 5's direction-independent items, each deployed when green; (5) Stage 6.
- **The deploy target is fad30e81** (12:55 Denver): CI on fa7e5f0a (#2097, the full run) was red
  on C4090's loop test and on the coverage ratchet (roundtrip.py's render-cache `clear()`
  reached by no unit test), so fad30e81 adds that test; 7fa974fa's run (#2099) was the docs-only
  set and is no code verdict (a docs-only commit runs the doc tests alone). Wait for GitHub's
  CI on **fad30e81**, read every job (coverage included), not only the tests.
- (Superseded: wait for GitHub's CI on 7fa974fa.) CI was about 20 runs behind at 12:20 Denver (4 at a time, ~26 min
  each). When it completes, read its failures (`scripts/nmas-ci-log failed`): if the only one is
  tests/test_v2_context_is_drawn.py::TestTheFixturesReachTheState::test_every_loop_drew_or_is_declared,
  deploy with `scripts/nmas-deploy --to fad30e81… --fast-lane "<CI run #, its result: only C4090's
  loop test failed, the operator's exception of 2026-11-24>"` (the fast lane keeps the window,
  preflight and smoke check; `--override-ci-red` cannot carry it: it needs another source
  green). Any other red: fix forward first, no exception for it. Log the deploy in the report.
- **Stage 2:** the under-10-minute target is DONE (587 s at 10 workers on 3f478dda). The serial
  run (one process, for the counts) started 12:20 Denver in an nmas-control tree; its log and
  JUnit file: `serial.log` and `serial.xml` in that session's scratch folder (gone after a reboot: then run it again). Compare its failures with
  the parallel run's (C4090's loop test only): any test failing serially alone is C4222's.
- design/proposals.zip exists (53 MB, 2026-11-23); the proposals are A Workbench, B Inbox,
  C Document.

## 00000000000. The 10:45 session (2026-11-24, from VS Code)

- **The overnight loop is retired** (the operator, 2026-11-24): START.md no longer writes a
  STATE word or restarts at 03:35. Sessions run from VS Code, whose label makes the namespace,
  so the hook's red-green runs and test changes commit. OPERATOR.md#session-namespace answered.
- **Everything that waited landed on main**, one commit per patch, hooks run (decisions file,
  10:45 lines, for each excuse):
  eac546ae c3886 · adfe287a c4207-c4208 · b6454600 c4205 · 2ab64859 c4090-reader ·
  c164dc6b c4195-c4196 · (c4081 already ccbdeceb) · d58e9cb9 c4200 · 96ef2a41 render-cache ·
  ab5f8be4 stage4-assistant · c55c9c54 stage5-settings-descriptions · 12856126 c4229 ·
  c12f21a6 c4228 · 05757d72 c4226 · 35f915d4 c4230 · ad4ac142 c4216 · 0c298581 c2820-held ·
  3d9e4595 c4231 · 73139098 c4232 · 7981f6f5 c2820-departs · 1c65f99b c2820-sdn ·
  480486c2 c2820-settings · 00f1fe69 c2820-ai-words · 500c03c9 c2820-codes ·
  d6c75170 c2820-labels · c285269a c2820-guards · cc2ff86d c2820-tiers ·
  4b3db80c c4234-measured · a64c1d38 c4234 · 41d1cf02 c2820-departs-rid · f430983a c4234-manual
  · edeaf472 c3601-coverage · 6cda46f4 c3601-pathtrace · 51184a35 c3601-fleetchange ·
  f91ba3f8 c3601-rotation · d030f04a c3601-save. Then 8cd85190 (C4234's two test defects the
  full suite found) and **fa7e5f0a** (C4237 to C4239, C3886's final review's MEDIUMs; its own
  device-write review SAFE, review-devicewrite-2026-11-24-c4237-c4239.md).
- `~/mercury-runs/*.patch` are all landed: do not apply them again. The worktree
  `~/nmas-worktrees/rulings-gui-kit` (branch rulings/gui-kit) is at fa7e5f0a, clean, behind main
  by this handoff's docs commit (`git merge --ff-only origin/main` there first).
- **Full suite on d030f04a** (scripts/nmas-control, 8 workers, worksteal, 639 s): 10 failed,
  32,045 passed, 425 skipped: C4090's loops (1), and C4234's two test defects (9), fixed in
  8cd85190 (131 passed). So main is red only on C4090 (OPERATOR.md#c4090-records): no deploy.
- **Browser tests and red-green:** the hook's runner cannot start Firefox (nor
  `nmas-test --allow-unconfined` here); CI's interpreter run directly can
  (`~/.local/share/nmas-py312/bin/python -m pytest`). Show a browser test red on its parent in
  an nmas-control tree with the parent's code and the commit's tests, then write its
  Guards-Existing trailer (the scratchpad's red_on_parent.sh did this; see decisions).
- **A test importing a name its commit adds to an existing module** at module level never
  collects on the parent and no trailer excuses it: import the module, read the name in the body.
- **Next:** read CI on fa7e5f0a (`scripts/nmas-ci-log main-ci`), fix forward any red but
  C4090's; then Stage 6: C3601's next callers (reads and the logging path, scoped in the 09:34
  section below), C4235's measurement; C4240 to C4242 are C.

## 0000000000. The 09:34 session (2026-11-24)

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **The stack's trees:** `~/mercury-runs/tree-stack-33.txt` (with c3601-pathtrace),
  `tree-stack-34.txt` (c3601-fleetchange), `tree-stack-35.txt` (c3601-rotation) and
  `tree-stack-36.txt` (c3601-save). Make the next patch against tree-stack-36; the worktree
  `~/nmas-worktrees/c2820-sdn` holds it staged. land_all.sh now ends
  `c3601-fleetchange c3601-rotation c3601-save` (36).
- **C3601's Save slice BUILT as a patch**, `~/mercury-runs/c3601-save.patch` and `.msg`:
  Save's job passes `page=` (Devices › Save, `job`), the page draws `save_page.job_card`, and
  Save's answer says its end in words. Device-write review SAFE
  (`~/Documents/nmas-reports/review-devicewrite-2026-11-24-c3601-save.md`); its two low
  findings fixed (a heading with no count, 200 for a refused job). Red first, four controls;
  aimed 189 files, C4090's loops the one red. **C4236** (new, C): three fidelity records end
  with stray `</content>` / `</invoke>` lines.
- **The opened mark is not missing:** In progress's Open the result posts `seen_run`
  (C3081) before it opens a page job's link, for a verified viewer; reviews keep raising
  it, it is kept.
- **C3601's scheduled rotation slice BUILT as a patch**, `~/mercury-runs/c3601-rotation.patch`
  and `.msg`: Rotate due devices now's job passes `page=` (Profiles, `rot_job` / `rot_run`),
  the tab draws the run's card (`_rotate_op`, lifted from the card route), and the answer
  carries `scheduled_rotation.outcome` (it said `ok` whatever the run did: a stopped run would
  have been green). Device-write review SAFE
  (`~/Documents/nmas-reports/review-devicewrite-2026-11-24-c3601-rotation.md`); its medium
  finding (a skipping run green) fixed in the patch. Red first, four controls; aimed 295
  files, C4090's loops the one red. **A UI test must press the control**
  (tests/test_presence_only.py): drive the POST, never the module's start function.
- **C3601's fleet change slice BUILT as a patch**, `~/mercury-runs/c3601-fleetchange.patch`
  and `.msg`: the plan's and both runs' jobs pass `page=` (`fleet_change.job_page`, the intent
  page with `plan_job` or `run_job`), the page draws that job's card above the layers (the
  card routes' bodies lifted out, `_plan_of_job` / `_run_of_job`), a paused run says "waits
  for your Go on". `ip.finished` now draws in the walk: its exemption removed and
  EMPTY_IN_FIXTURE_CEILING 325 → 324. Red first, three controls; aimed 210 files, 6,511
  passed, C4090's loops the one red. **Device-write review SAFE**
  (`~/Documents/nmas-reports/review-devicewrite-2026-11-24-c3601-fleetchange.md`); it found
  **C4235** (new, UNKNOWN): a paused run's Go on can be pressed twice.
- **Aimed sets must include tests/test_v2_context_is_drawn.py** when a page job's page changes
  (the walk's providers start jobs): the path trace set did not; the walk starts no trace, so
  it is unaffected, and the fleet change set (on top of it) ran it.
- **C3601's path trace slice BUILT as a patch**, `~/mercury-runs/c3601-pathtrace.patch` and
  `.msg`: the trace's job carries Topology opened on the trace as its page (built by
  `topology_page.qs`), and its answer carries the new `path_trace.outcome` (done "delivered" /
  "leaves the network", stopped "N of M branches not delivered", failed). Its answer was the
  trace's id only, the same red-"no reason" trap. Red first, three controls; aimed 195 files, 6,045 passed, 66 skipped, none red
  (541 s at -n 4).
- **Next:** land the 36 once session-namespace is answered; meanwhile C3601's next callers,
  each as a patch against tree-stack-36, or C4235's measurement. Scoped:
  - **Reads and the logging path** (`modules/nsot/reads.py:1076`, `logging_path.py:386`):
    both open `/v2/show-commands/run/<run>?job=…&list=…` (`reads_v2.show_commands_result`,
    the page a `page=` should name), and both answer only `{"run": id}`: the red "refused:
    no reason" trap. Each needs its own outcome from its record: reads' `summary.by_state`
    (answered / failed / skipped / unknown); the logging path's results (received / not
    received / not sent / unknown). One helper building the link, two outcomes.
  - **The capture preview** (`routes/golden.py:361`, its one caller the device page's
    Capture, `routes/device_v2.py:1052`): a device-page card, so it is `device=` and
    `card="capture"` on the job, `"capture"` added to `device_actions.REOPENS` and `job_card`
    (`capture_card` needs the viewer's confirm part, which `job_card` has no request for):
    larger than the page-job slices.
  - Then an app's deploy (`modules/apps/deploy_op.py:778`) and adopt (`routes/adopt_v2.py:112`).

## 000000000. The 09:06 session (2026-11-24): read this first

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **The stack's trees:** `~/mercury-runs/tree-stack-31.txt` (with c4234-manual) and
  `tree-stack-32.txt` (with c3601-coverage). Make the next patch against tree-stack-32; the
  worktree `~/nmas-worktrees/c2820-sdn` holds it staged. land_all.sh now ends
  `c2820-departs-rid c4234-manual c3601-coverage` (32 patches).
- **C3601's template coverage slice BUILT as a patch**, `~/mercury-runs/c3601-coverage.patch`
  and `.msg`: the check's job carries the Coverage tab as its page, the tab draws the job from
  `job`, and the job's answer says `ok`. **A trap for the next callers:** a page job's finished
  row is green only when its payload says `ok` or has a `state` in `in_flight.PAGE_LEVELS`;
  coverage's said neither, so it would have been drawn red "refused: no reason". In progress
  names a page job by its `kind`, so a kind must be words. Red first, three controls; aimed
  140 files, 4,155 passed, C4090's loops the one red. Nine callers left (the row lists them).
- **C4234's manual pass BUILT as a patch**, `~/mercury-runs/c4234-manual.patch` and `.msg`:
  the manual's 34 code passages in 18 pages and two diagrams' labels (modules/manual_diagrams.py,
  SVGs rewritten by scripts/nmas-manual-diagrams) in words; tests/test_codes_drawn.py's
  manual exclusion removed, its floor now a planted response through `v2_context._Recorder`.
  Red first (the stack's manual: 67 places, the 67 measured), two controls bite; aimed 77
  files, 2,969 passed, C4090's three loops the one red.
- **C2820 item 31 deferred** (decisions file): its text is not recorded, and its candidates are
  in modules/heal/dampening.py (device-write path). **C2820 has nothing else left.**
- **Next:** land the 32 once session-namespace is answered; meanwhile C3601's next caller
  (path trace, `modules/path_trace.py:542`), each as a patch against the newest stack tree.

## 00000000. The 08:22 session (2026-11-24)

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **The stack's trees:** `tree-stack-27.txt` (with c2820-tiers), `tree-stack-28.txt` (with
  c4234-measured), `tree-stack-29.txt` (with c4234), `tree-stack-30.txt` (with
  c2820-departs-rid). Make the next patch against tree-stack-30; the worktree
  `~/nmas-worktrees/c2820-sdn` holds it staged. land_all.sh now ends
  `c2820-tiers c4234-measured c4234 c2820-departs-rid` (30 patches).
- **A stack defect found and fixed as a patch** (`c2820-departs-rid.patch`): item 9's patch
  changed the duplicate router-id row to "differs from its intent" and left
  tests/test_duplicate_router_id.py expecting "departed" (red on tree-stack-26). Earlier
  aimed sets missed it: **aimed runs over 300 s need `NMAS_TEST_TIMEOUT` raised** (the
  default bounds the whole run: 407 files took 700 s at -n 4 with 2400).
- **C2820 item 27 BUILT as a patch**, `~/mercury-runs/c2820-tiers.patch` and `.msg`: Fix kinds'
  chips say who fixes each kind ("Mercury by itself", "A person approves", "No configuration
  fix", "A person only"), the tier on hover; the security row drew "4 never" (a template
  else) and now "A person approves". Red first, two controls; aimed 39 files, 1,624 passed,
  C4090's loops the one red. **C2820 left:** only 31's `dampening` backtick.
- **C4234 measured, UNKNOWN to B** (`c4234-measured.patch`, docs only): the walk's 2,015
  responses draw 17 distinct codes in 11 templates' words; the manual 38 in 18 pages.
- **C4234 BUILT as a patch**, `~/mercury-runs/c4234.patch` and `.msg`: the 17 in words, and
  tests/test_codes_drawn.py over every response the walk reads (a `codes` scan in
  tests/v2_context.py's recorder). Red first (51 places), two controls bite; four tests'
  premises corrected (they asserted the code itself in the words); aimed 407 files, 11,733
  passed, C4090's loops the one red left. Kept outside the
  scan: the manual, the running commit's subject, a console profile's description (hashed:
  changing it asks surveyed devices to survey again; decisions file).
- **Next:** land the 30 once session-namespace is answered; meanwhile C4234's manual pass
  (38 codes in docs/manual), C2820 31's backtick, or Stage 6's rows.

## 0000000. The 07:48 session (2026-11-24)

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **The stack's trees:** `~/mercury-runs/tree-stack-24.txt` (with c2820-codes),
  `tree-stack-25.txt` (with c2820-labels) and `tree-stack-26.txt` (with c2820-guards). Make
  the next patch against tree-stack-26; the worktree `~/nmas-worktrees/c2820-sdn` holds it
  staged (its index is tree-stack-26). land_all.sh now ends
  `c2820-codes c2820-labels c2820-guards` (26 patches).
- **C2820 item 29 BUILT as a patch**, `~/mercury-runs/c2820-guards.patch` and `.msg`: the
  hard stops' labels say what they count ("a flap: times one interface went down or up", no
  "updown", no "sections a heal"). Red first, two controls bite; aimed 34 files, 1,486 passed.
- Kept (decisions file): "Dry run" (the operator's word), item 35's sentence and "golden",
  item 33's check names. **C2820 left:** item 27 (Tier words), 31's `dampening` backtick.
- **C2820 items 32 and 34 BUILT as a patch**, `~/mercury-runs/c2820-codes.patch` and `.msg`:
  no Settings screen's visible text names a register row, a plan section or "the AUTO
  production-readiness gate" (new tests/test_settings_words_name_no_codes.py over every
  Settings screen; Auto's preview checks in test_heal_policy). Red first (12), a control
  bites; aimed 168 files, 4,713 passed, C4090's loops the one red. sdn-settings and sdn
  fidelity records compared by the diff. **C4234 (new, UNKNOWN):** the same codes in 339
  string constants outside Settings, how many drawn unmeasured (its one measurement in the row).
- **C2820 item 26 BUILT as a patch**, `~/mercury-runs/c2820-labels.patch` and `.msg`:
  "Check the certificate", "Token sent as", "VMs whose backups are checked", "Listen
  address". Red first (3), a control bites; aimed 85 files, 3,392 passed, C4090's the one red.
- Kept (decisions file): item 30's hashes (what a confirm binds), the AI classes' names.
- **Next:** land the 26 once session-namespace is answered; meanwhile C2820's item 27 (Tier
  words: check first whether "Tier 1/2" is the operator's or the plan's naming, as "Dry run"
  was), or C4234's measurement (the CODE scan over Needs attention, History, the device page,
  DHCP, SDN and Coverage rendered on the suite's fixtures), or Stage 6's rows.

## 000000. The 07:11 session (2026-11-24)

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md).
- **The stack's trees:** `~/mercury-runs/tree-stack-20.txt` (all 20 patches, made by
  applying c4232 and c2820-departs onto tree-stack-18) and `tree-stack-21.txt` (with the new
  one; 22 and 23 with the next two). Make the next patch against tree-stack-23
  (`git read-tree -u --reset <tree>` in a
  fresh worktree, then `git diff --cached --binary <tree>`).
- **C2820 items 15 and 16 BUILT as a patch**, `~/mercury-runs/c2820-sdn.patch` and `.msg`
  (worktree `~/nmas-worktrees/c2820-sdn`, staged): SDN's Needs attention rows and SDN ›
  Responses name the switch (one namer, `sdn_ops_page.switch_namer`, lifted from
  `incident_rows`), the action by its catalogue label and the escalation threshold by its
  setting's title; ids and keys in the row's operands or on hover; the attack row loses
  "C2279:" and its ids. Red first (17 tests), four controls bite; aimed 114 files, 3,429
  passed, the one red C4090's loops. docs/fidelity/sdn.md compared by the diff, one approval
  log line. Not device-write (display only).
- **C2820 item 25 in part BUILT as a patch**, `~/mercury-runs/c2820-settings.patch` and
  `.msg` (same worktree, against `tree-stack-21.txt`; `tree-stack-22.txt` is the stack with
  it): a `setting_label` filter (routes/v2.py, over `settings_page.field_label`) names each
  field in Settings' save notices and a switch preview as its card labels it, the key on
  hover. Red first (3 tests), a control bites; aimed 26 files, 817 passed, C4090's loops the
  one red. docs/fidelity/settings.md compared by the diff. land_all.sh now ends
  `c2820-departs c2820-sdn c2820-settings` (22 patches).
- **C2820 item 25, Settings › AI, BUILT as a patch**, `~/mercury-runs/c2820-ai-words.patch`
  and `.msg` (same worktree, against `tree-stack-22.txt`; `tree-stack-23.txt` is the stack
  with it): an `ai_feature` filter (routes/v2.py, over `background.FEATURES`' words) names
  the feature in Settings › AI's on, off, already-off and caps notices, its Turn on heading
  and the spend panel's Turn off answer, the key on hover. Red first (6 tests), a control
  bites; aimed 79 files, 2,789 passed, C4090's loops the one red. Two fidelity records
  compared by the diff. land_all.sh now ends `c2820-sdn c2820-settings c2820-ai-words`
  (23 patches).
- **Next:** land the 23 patches once session-namespace is answered; meanwhile C2820's items
  26 to 35 (Settings' labels and tier words), or "departed" in self-healing's words; or
  Stage 6's rows. New patches against tree-stack-23.

## 00000. The 06:10 session (2026-11-24)

- **Still blocked the same way** (label `unconfined`, no answer in OPERATOR.md). This
  session's host read was refused too (`Permission denied (publickey)`: no SSH key in its
  environment), so Stage 6's host page times were not measured; not retried.
- **The stack's tree is recorded**, `~/mercury-runs/tree-stack-18.txt` (`git write-tree` of
  the landing worktree's 18 staged patches on 012526a8): new patches are made against it
  (`git read-tree -u --reset <tree>` in a fresh worktree, then `git diff --cached --binary
  <tree>`), and `~/mercury-runs/fidelity_mismatch.py <tree>` lists every fidelity record a
  patch left stale.
- **C2820 item 9 ("departs") BUILT as a patch**, `~/mercury-runs/c2820-departs.patch` and
  `.msg` (worktree `~/nmas-worktrees/c2820-departs`, staged): a device off its intent is said
  to differ, the lines in words (`intent_match.said`, `state_said`), on the Devices badge
  (short, lines on hover), device page, History, capture, Save All denial, Needs attention,
  diagnoses, guard 4 and the decision's words for new records, seven templates, six manual
  quotes, five fidelity records compared again. Red first, three controls bite; aimed 8,712
  passed, the only red C4090's loops. Its act.py change is a refusal's words only; it goes to
  the device-write review with C4232. land_all.sh now ends `c2820-departs`.
- **C4232 (new): the fleet change run and the read-only account rollout drew no stepper while
  running** (the batch deploy draws one over the same engine): **fixed as a patch**,
  `~/mercury-runs/c4232.patch` and `.msg` (worktree `~/nmas-worktrees/c4232-waves`, staged;
  scratch `~/mercury-runs/c4232-scratch/`): deploy_job's recorder lifted out as `track` /
  `track_wave` and its rows as `_live_rows` / `_ended_row`, `waves_card` drawing both runs;
  read_account's `_PROGRESS` and text line gone. Red first, 7 controls; aimed 1,507 passed
  (C4090's loops the one red). Its two fidelity records compared against their own words
  (boards not on the machine) and FC5/R5 logged as one deviation. land_all.sh now ends
  `c4232 c2820-departs` (20 patches; both checked to apply in that order).
- **The device-write review of both: SAFE**
  (`~/Documents/nmas-reports/review-devicewrite-2026-11-24-c4232-c2820-departs.md`). Its
  MEDIUM fixed in c4232.patch: the two runs announce `device_progress` (`ENGINE_PROGRESS`),
  never `deploy_job`, which wakes the `rip` and `endpoints` readers (sessions to every device
  mid-rollout); tested, a control bites. The batch deploy's own case registered as C4233
  (UNKNOWN, its measurement named). Its LOWs are in the report, not worked.
- **Next:** land the 20 patches once session-namespace is answered (land_all.sh order), then
  one full suite; meanwhile Stage 5's human-readable leftovers (the heal record words saying
  "departed" need captured records; SDN catalogue keys; Settings) or Stage 6's rows.
- Items 11 ("start not tracked", the operator's words) and SDN's mode names kept: decisions
  file.

## 0000. The 04:49 session (2026-11-24)

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

- (06:10 session) main is 219e6faf plus this session's handoff commit (pushed); 20 patches
  wait (land_all.sh). Nothing deployed.
- (earlier) main is f9ec3f88 plus this session's handoff commit (pushed). Nothing deployed. Main's CI
  red as before (#2030: C3886's test_heal_act, C4090's loops). Full suites this session: two
  over the landing stack, 12 workers (775 s and 780 s).
