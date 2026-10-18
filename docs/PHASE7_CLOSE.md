# Closing Phase 7

Written 2026-10-18, 18:36 UTC, for the operator, to close Phase 7 today. Phase 7's operating
mode (CLAUDE.md) and its burn-down (docs/PHASE7_BURNDOWN.md) are what this closes. Times are UTC,
with MDT (UTC−6) beside where it helps.

## Where it stands

*Updated 2026-10-18 22:5x UTC, after the operator's P7-27 walk.*

**The host runs fd1ec370** (CI #945), deployed 2026-10-18 at 22:51:54 UTC. Its GET walk passed 23
of 23 paths: `/` answers 302 to `/v2/`, keeping `?list=`; today's old addresses answer 404, drawn
in v2's look for a browser; every v2 page answers 200.

**Done:**
- P7-27 is merged (4e631168), deployed and walked by you; steps 1 to 12 PASS.
- 7.8 and 7.D are closed in the writeup.
- C650 (About) and C1267 are closed.
- Your walk's four fixes are deployed: C1303, C1304, C1305 and C1306.

**Phase 7 now waits only on your decisions** (below): C1192, built or deferred; and two new Bs,
C1315 (a GitHub edit) and C1317 (the backup window in code), each waiting on a rule from you.

## What is done today (2026-10-18), on main

| Commit (UTC) | What | CI | On the host |
|---|---|---|---|
| fd1ec370 (22:42) | C1304, C902: Devices' select-all box; all matching resolved by each action on the server | #945 success | yes |
| 9205ba01 (22:34) | C1303: History's Kind filter, goldens one click away, on the device tab and the History page | #944 success | yes |
| e5cc8840 (22:28) | C1305, C1306: Coverage cells never blank, a decline its own mark; the failure page in v2's look; C1314 to C1316 from the operator's questions | #943 success | yes |
| ee1f85f7 (22:17) | P7-27's walk closed: About recorded (C650), 7.D closed, C1267 and C1294 closed; About's footer fixed (C1313); C1260's bound measured | #942 success | yes |
| c9b263d8 (21:39) | STANDING_APPROVAL_LOG: the operator's decisions of 2026-10-18 evening, each traced | #941 success | yes |
| 305bdcbf (21:33) | C1294: on main every commit is its own CI concurrency group, so no main commit loses its run | #940 success | yes |
| 350fd6cd (21:27) | CLAUDE.md: P7-27's post-merge lines and Lab 7's lessons link; docs/LESSONS.md "Lab 7's lessons, kept" | #939 success | yes |
| c60a7a54 (20:05) | C1265: mutant 331 killed (the pipeline is handed the network the apply named); 3 left to judge | #938 success | yes |
| a91e03c5 (19:59) | C1265: apply_batch's last 250 mutants run; 11 VERDICT survivors killed, 4 left to judge | #937 success | yes |
| 00a66cac (18:39) | docs/PHASE7_CLOSE.md: the checklist to close Phase 7 today | #936 success | yes |
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

1. **Decide C1192**: build it now, or defer it explicitly (the agent's three-line account is in
   the session).
2. **Choose C1315's rule** (an edit on GitHub): the remote refuses every writer but Mercury (a
   GitHub branch protection, yours), or v2 adopts the remote's commits by a confirmed operation.
3. **Paste the replacement** for CLAUDE.md's "Never send the operator to today's (v1) pages"
   bullet (the text is in the session).

Done since: your P7-27 walk (steps 1 to 12 PASS, the six divergences kept), and About's
screenshot.

Done since this was first written: the CLAUDE.md script ran and its lines are committed with
"Lab 7's lessons, kept" (350fd6cd); the inferences are decided (below); C1294 is built and shown
(305bdcbf).

**Done by the agent after your walk:**
- About recorded, and C650 closed.
- 7.D closed in the writeup; C1267 closed (ee1f85f7).
- Your walk's four fixes, each gated and deployed: C1303 History's Kind filter (9205ba01); C1304
  Devices' select-all (fd1ec370); C1305 Coverage never blank; C1306 the failure page (e5cc8840).

The burn-down's last items are done: P7-09's 7.D, C650 and P7-27. **Phase 7 closes when C1192
is built or deferred by your word.** C1315 is a new B, waiting on your rule; say whether it is
in Phase 7 or after.

## Every A and B: how each was resolved

The baseline is 318cf42f (2026-10-17 22:22 MDT, 04:22 UTC on 2026-10-18), the last commit before
the overnight run. The register then held **6 A and 19 B**. Every row below is one of those, or
was opened since.

**Who placed the deferred rows:**
- **The charter triage**, approved by the operator on 2026-10-07, placed most of them.
- **The burn-down's "Out of Phase 7"** (docs/PHASE7_BURNDOWN.md section 4, written in 418ab3ce
  on 2026-10-15) holds the rest. The operator decided its D1 to D6 categories that day, as
  recommended. Its row-by-row placements are the agent's, and are said as such.

### The 6 A rows

| Row | Resolution |
|---|---|
| C650 | **Closed: ee1f85f7.** About's record came from your walk screenshot: 28 screens and 3 components are recorded. The 11 screens no walk touched are their own C row, C1302, Stage 7's tail by the burn-down's decision. 7.D closed with it. |
| C139 | **Deferred, by the operator (the 2026-10-07 triage):** CORE, NetBox Phase 1, deferred (L). Burn-down section 4: "NetBox Phase 1, after cutover". |
| C552 | **Deferred, by the operator (the triage):** CORE, NetBox Phase 1, which removes the interface-counter Drained. Burn-down section 4: the same. |
| C551 | **Deferred, by the operator (the triage):** FUTURE; NetBox's Drained status is the fact. Burn-down section 4: "After Phase 7". |
| C781 | **Deferred, by the operator:** mutation testing is parked (C835; CLAUDE.md: "Mutation testing is parked"; the burn-down's section 4: no nights run until the operator says Phase 7 has settled). |
| C842 | **Deferred, by the operator:** mutation parked, as C781. |

### The 19 B rows

| Row | Resolution |
|---|---|
| C1160 | **Closed: 11b0a1ef** (the Inventory source card names what NetBox left out). |
| C1168 | **Closed: 898d1bad** (the rotation halt takes the operator's two-strikes rule). |
| C1259 | **Closed: 2b78a931** (an unreadable NetBox-sourced list is a Needs attention row; deployed in 898d1bad). |
| C1192 | **Open, for the operator's decision:** build now, or defer explicitly, on the agent's three-line account (2026-10-18). |
| C7 | **Deferred, by the operator (the triage):** FUTURE (7.7). Burn-down section 4: after cutover. |
| C60 | **Deferred, by the operator (the triage):** FUTURE (Stage 8's follow-up window). Burn-down section 4: "Phase 8 / Stage 8". |
| C230 | **Deferred, by the operator (the triage):** FUTURE; the operator's one-time step. Burn-down section 4: "Stage 9, security" (D4). |
| C472 | **Deferred:** the triage placed it CORE, Stage 7. The burn-down placed it "multi-user, after cutover", Stage 7's tail: the agent's placement under the operator's D3. |
| C531 | **Deferred, by the operator (the triage):** FUTURE. Burn-down section 4: "After Phase 7". |
| C554 | **Deferred, by the operator (the triage):** FUTURE, with the parked removal work. Burn-down section 4: "After Phase 7". |
| C556 | **Deferred, by the operator (the triage):** CORE, NetBox Phase 1, after cutover. |
| C559 | **Deferred, by the operator (the triage):** CORE, NetBox Phase 1, after cutover. |
| C561 | **Deferred, by the operator (the triage):** FUTURE. Burn-down section 4: "After Phase 7". |
| C563 | **Deferred, by the operator (the triage):** CORE, Phase 2 (revert by reload). |
| C618 | **Deferred, by the operator (the triage):** CORE, Phase 2. |
| C792 | **Deferred, by the operator:** mutation parked (C835). |
| C834 | **Deferred, by the operator:** mutation parked (C835). |
| C822 | **Deferred:** burn-down section 4, "Harness and measurement only". The agent's placement under the operator's D5. |
| C828 | **Deferred:** burn-down section 4, "Stage 9, functional or minor". The agent's placement under the operator's D4. |

### Opened since 318cf42f

| Row | Bucket | Resolution |
|---|---|---|
| C1268 | A | **Closed: a09c6e4d**, opened and fixed in one commit; deployed 06:49 UTC. |
| C1263 | B | **Closed: df2d2397**, deployed. |
| C1276 | B | **Closed: 781b8bf1**, opened and fixed in one commit. |
| C1270 | B | **Closed: 4ef1dcb4**. |
| C1274 | B | **Closed: 11b0a1ef**. |
| C1271 | B | **Closed: 30d096d3** (found UNKNOWN, measured B). |
| C1273 | B | **Closed: d25b5d19** (found UNKNOWN, measured B). |
| C1269 | B | **Closed: 3e8bc747**. |
| C1277 | B | **Closed: 3e8bc747**. |
| C1287 | B | **Fixed: db204840. Closed: 9ae340f0** (once a Markdown-only commit's own run, #927, was seen). |
| C1260 | B | **Re-ranked C to B by the operator.** Fixed: 1b08287f. Its bound was measured under the reproduced load and set at 12 s (ee1f85f7). |
| C1267 | B | **Closed: ee1f85f7.** P7-27 merged (4e631168) and deployed; your walk passed, steps 1 to 12. |
| C1313 | B | **Closed: ee1f85f7.** About's footer claimed a host behind is always a row (found by your question 7). |
| C1303 | B | **Closed: 9205ba01.** History's Kind filter, goldens one click away (your walk). |
| C1304 | B | **Closed with C902: fd1ec370.** Devices' select-all; all matching is resolved by each action on the server (your walk). |
| C1315 | B | **Open, for your rule:** an edit on GitHub has no v2 path. Mercury never fetches, and the divergence row sends a person to a terminal. Either the remote refuses every writer but Mercury (GitHub branch protection, outside the lab, yours), or v2 adopts the remote's commits by a confirmed operation (found by your question 9). |
| C1317 | B | **Open, for your answer:** this lab's backup window (08:30 to 09:10 UTC) is a constant in product code (`scheduled_rotation.BACKUP_WINDOW`), against "nothing lab-specific in the product". The fix is no-change windows as a setting, empty by default, its shape the bulk design's question 5 (found by C1307's design). |

### In all

- **Of the 6 A:** C650 is closed (ee1f85f7). 5 are deferred by your decisions: the triage, and
  mutation parked.
- **Of the 19 B:** 3 are closed. 1 waits on your call (C1192). 12 are deferred by the triage or
  the parked mutation. 3 are deferred by the agent's placement under your D-categories (C472,
  C822, C828).
- **Since then:** 17 opened, 1 A and 16 B. 15 are closed. 2 are open: C1315, waiting on
  your rule, and C1317, waiting on your answer to the bulk design's question 5. One UNKNOWN may become a B: C1316, s3's heartbeat tail, waiting on one measurement.

## The inferences, as the operator decided them (2026-10-18, by 21:20 UTC)

1. **P2:** confirmed.
2. **C1287:** confirmed.
3. **The video dry-run:** confirmed. The operator rehearses the demos.
4. **The mechanisations after Phase 7:** confirmed.
5. **P7-27 merged before its CLAUDE.md lines:** confirmed. The lines are in (350fd6cd).
6. **C1294:** confirmed, and built: 305bdcbf. Shown by two quick pushes running at once, #940
   and #941, both green, neither cancelled.
7. **About's record from the walk:** confirmed.
8. **C1192:** the operator decides build now or an explicit deferral, on the agent's three-line
   account. It stays in Phase 7 until then.
9. **C1260's 30 s:** a guess, said the operator. The finishing probes are measured under the
   reproduced load (a gate beside a mutation run, load average to 28.5), and the bound is set
   at 2.5 times the slowest measured.

Each is a line in docs/STANDING_APPROVAL_LOG.md (c9b263d8).

## Not done, and why

- **docs/LESSONS.md's "Lab 7's lessons, kept"**: written, waiting for CLAUDE.md's `[why]` link
  (your script, step 2 above); tests/test_claude_md.py needs both in one commit.
- **Lab 7's mechanisations** C1289 to C1293 (about 12 to 15 h in all), after Phase 7 (inference 4).
- **C1265's rest**: 250 of `apply_batch`'s mutants unrun (1 h 40 min to 4 h of runner time).
- **C1294's fix** (the CI workflow: inference 6); **C1288** (a test reading the checkout's real
  log); the seven C defects C650's records found (C1295 to C1301), each a fidelity-held template.
- **CLAUDE.md's four post-merge lines**: your script.
