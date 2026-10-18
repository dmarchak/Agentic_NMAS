# Closing Phase 7

Written 2026-10-18, 18:36 UTC, for the operator, to close Phase 7 today. Phase 7's operating
mode (CLAUDE.md) and its burn-down (docs/PHASE7_BURNDOWN.md) are what this closes. Times are UTC,
with MDT (UTC−6) beside where it helps.

## Where it stands

The host runs **ab1909d2** (CI #935), deployed 2026-10-18 18:33:56 UTC, its GET walk passed
23 of 23 paths as expected (`/` 302 to `/v2/` keeping `?list=`, today's old addresses 404, every v2 page 200). P7-27, the last of today's (v1) pages, is merged (4e631168) and deployed: the
removals (7.8) are done. Three things are left, and two of them are yours: the P7-27 walk, the
CLAUDE.md script, then About's record and 7.D's close, which follow your walk.

## What is done today (2026-10-18), on main

| Commit (UTC) | What | CI | On the host |
|---|---|---|---|
| ab1909d2 (18:16) | 7.8 closed in the writeup: P7-27 merged and deployed; 7.D's three records noted | #935 success | yes |
| 1b08287f (18:10) | C1260: the probes that finish run under a measured bound; the gate's 5 s flake fixed | #934 success | yes |
| be578a3c (18:03) | C650: Save, the pending page and the retired record compared with their boards; C1295 to C1301 | #933 success | yes |
| cdbad6dd (17:51) | P7-27's walk names its release and About's screenshot; C1294 registered | #932 success | yes |
| 4e631168 (17:43) | P7-27 merged into main: the last of today's (v1) pages removed; / answers 302 to /v2/ (C1267) | #931 success | yes |
| a9169193 (17:37) | Lab 7's practices made standing in docs/TESTING.md; C1289 to C1293 register what to mechanise | #930 cancelled by a newer run (C1294); its descendants passed | yes |
| 9ae340f0 (17:31) | C1287 closed: a Markdown-only commit's own run shown; Lab 7 closed (the operator); C1288 registered | #929 success | yes |
| f58cef18 (17:25) | CLAUDE.md: a failing test reports a real problem (the operator's bullet, Lab 7 closed) | #928 success | yes |
| 64414d56 (17:05) | C1260: re-ranked B (the operator, 2026-10-18), fixed this week; retried openly until then | #927 success | yes |
| db204840 (16:59) | C1287: every push runs CI; a Markdown-only commit no longer escapes test_claude_md and job a | #926 success | yes |
| 41fe5174 (10:38) | C1265: the fingerprint's and the loader's unrun mutants; a fresh install's first profile held by a test | #925 success | yes |
| e29cd86f (09:07) | C1265: apply_batch's "the confirmed program moved" sample run; its one VERDICT survivor killed | #924 success | yes |
| 3e8bc747 (08:35) | C1277, C1232, C1269: v2 draws a silenced alert, saves the devices with no golden, and chooses a profile's version | #922 success | yes |
| d25b5d19 (08:28) | C1273: v2's capture result is amber for a device departing from intent, never green | #921 success | yes |
| 30d096d3 (08:17) | C1271: a source not read within its promise is a Needs attention row, never a quiet page | #920 success | yes |
| 4ef1dcb4 (08:03) | C1270: v2's deploy cards draw verify's scope, the lines read back and each not read back | #919 success | yes |
| 11b0a1ef (07:51) | C1274, C1160: v2's loops are held to what the test data reaches; the Inventory source card names what NetBox left out | #918 success | yes |
| c1fe3b69 (07:26) | C1265: the two unlistable equivalent mutants removed by making them impossible | #917 success | yes |
| 781b8bf1 (07:10) | C1276: a run that found nothing due no longer clears the rotation halt | #916 success | yes |
| ac0c3847 (06:57) | CLAUDE.md: item d's bracket names its check; two citations no longer name the v1 check | none (a Markdown-only push then ran no CI: C1287) | yes |
| a09c6e4d (06:38) | C1268: a rollback that did not restore the device is never headed "Rolled back" | #915 success | yes |

The branch `p7-27` (e2f27b84, 078c1bd0) is in main through the merge 4e631168.

## What only you can do, in order

1. **Walk P7-27** (docs/walks/P7-27.md, about 30 to 40 minutes): 12 read-only steps, each with
   its PASS line; at step 12, the About screenshot it describes, saved as
   `<home>/Documents/nmas-reports/P7-27-2026-10-18/about.png`; then section D's six board
   divergences, each "keep" or "change". Paste your results into the session.
2. **Run the CLAUDE.md script** (2 minutes), on your laptop:

   ```
   python3 ~/Documents/nmas-reports/claude-md-p7-27-merge.py
   ```

   PASS: its last line starts `DONE: 5 edits applied; the file as it was is kept at`, after a
   unified diff of five changes (P7-27's four post-merge lines, and the `[why]` link of the
   failing-test bullet to "Lab 7's lessons, kept"). If it prints `REFUSED:`, nothing changed;
   paste what it printed. Then say so: the agent commits CLAUDE.md with docs/LESSONS.md's new
   section (tests/test_claude_md.py needs both together).
3. **Confirm or correct the inferences** below (about 10 minutes).
4. **Say yes or no to C1294's fix** (it changes the CI workflow, which you asked to hear of
   first): one concurrency group per commit on main, so no main commit loses its verdict.

After 1 to 3 the agent: records About (C650), closes 7.D in the writeup, closes C1267, commits
CLAUDE.md with the lessons, deploys and walks. **Phase 7 then closes**: the burn-down's last
items (P7-09's 7.D, C650, P7-27) are done.

## Every open A and B row, and why it is still open

Phase 7's own:

| Row | Bucket | Why open | What closes it |
|---|---|---|---|
| C1267 | B | P7-27 is merged and deployed; your walk has not run | your walk |
| C650 | A | About's record waits on your screenshot; 27 screens are recorded (and 3 shared components), and 11 more go to Stage 7's tail by the burn-down's decision, compared from board shots with no walk | the screenshot, then the agent |

Outside Phase 7, each placed by the charter triage of 2026-10-07 or by its own row:

| Row | Bucket | Where it was placed |
|---|---|---|
| C552 | A | CORE, NetBox Phase 1 (the charter triage, 2026-10-07): the interface-counter Drained removed, NetBox's Drained shown with its source and age |
| C139 | A | CORE, NetBox Phase 1, deferred (L): a retired device escapes every fix; coupled with C143 |
| C781 | A | the mutation nightly, parked by the operator (C835): survivors of the AI family's moved helpers, triaged by function when the nightly runs |
| C842 | A | the coverage and mutation nightlies, parked (C835): `history_ask.alternation`'s mutants turn a night red |
| C551 | A | FUTURE (the triage): Drained measured by a counting ACL is deferred; NetBox's Drained status is the fact |
| C556 | B | CORE, NetBox Phase 1: NetBox as the source of truth for devices on every network Mercury onboards |
| C559 | B | CORE, NetBox Phase 1: the import writes every device's type as "Unknown" |
| C472 | B | CORE, Stage 7's tail (the triage): live regions losing a person's state on another person's write |
| C563 | B | CORE, Phase 2: the TFTP responder answers from the routed address |
| C618 | B | CORE, Phase 2: the revert's TFTP and ZTP cannot both hold udp/69 |
| C531 | B | FUTURE: revert as one action by measured removal (Phase 2 reverts by reload) |
| C561 | B | FUTURE: restore by configure replace |
| C554 | B | FUTURE: Mode B and IPv6 ACL entries, with the parked removal work |
| C60 | B | FUTURE: the deploy follow-up window (Stage 8) |
| C7 | B | FUTURE: defaults frozen by the 2026-09-23 settings erasure (7.7) |
| C230 | B | FUTURE: Grafana's token is an Editor's; the operator's one-time step |
| C792 | B | the mutation nightly, parked (C835) |
| C834 | B | the mutation nightly, parked (C835) |
| C822 | B | the test harness (a clock patch hides a hang), after Phase 7 by the burn-down's D5 (harness work out of Phase 7) |
| C828 | B | History › Query's Code mode, a v2 improvement after Phase 7 (D5) |
| C1192 | B | Needs attention keeps no "recently cleared" history: your B from the walks (2026-10-17), not in the burn-down; placed after Phase 7, **inferred, unconfirmed**: say if it belongs in Phase 7 |

## Inferences waiting for your confirmation

Each is a line in docs/STANDING_APPROVAL_LOG.md marked "inferred, unconfirmed" or "the agent's
recommended option". Say "confirmed" or what to change, by number.

1. **C1265, P2** (overnight): the hand mutant P2 was a redundant clause, not a default, so
   "make it impossible" was read as removing that clause from `profile_apply_confirm`.
2. **C1287** (the agent's option): every push runs the whole CI, rather than a second, lighter
   workflow for Markdown-only commits.
3. **Lab 7's video dry-run** (/tmp/lab7demo-check) was not run: nothing defines it, the folder
   does not exist, and Lab 7 is closed. Say what it was if it is still wanted.
4. **Lab 7's five mechanisations** (C1289 to C1293) wait until Phase 7 closes; their docs and
   rows are in.
5. **P7-27 merged without its four CLAUDE.md lines**: the merge's gate did not need them, so the
   condition "if its gate needs them first, don't merge" did not hold. They are your script.
6. **C1294 registered, not fixed**: its fix changes the CI workflow, which you asked to hear of
   before any change beyond C1287.
7. **About's record** (C650) comes from the screenshot in the P7-27 walk's step 12, so 7.D's
   close follows your walk.
8. **C1192** (Needs attention keeps no "recently cleared" history; your B from the walks) is
   placed after Phase 7: it is not in the burn-down.
9. **C1260's bound** for the probes that finish is 30 s, about 8x the measured slowest,
   past the usual 2.5x, because the loaded top that failed (over 5 s) is not measured; the
   commit carries a `Test-Weakened:` line so the change is seen.

## Not done, and why

- **docs/LESSONS.md's "Lab 7's lessons, kept"**: written, waiting for CLAUDE.md's `[why]` link
  (your script, step 2 above); tests/test_claude_md.py needs both in one commit.
- **Lab 7's mechanisations** C1289 to C1293 (about 12 to 15 h in all), after Phase 7 (inference 4).
- **C1265's rest**: 250 of `apply_batch`'s mutants unrun (1 h 40 min to 4 h of runner time).
- **C1294's fix** (the CI workflow: inference 6); **C1288** (a test reading the checkout's real
  log); the seven C defects C650's records found (C1295 to C1301), each a fidelity-held template.
- **CLAUDE.md's four post-merge lines**: your script.
