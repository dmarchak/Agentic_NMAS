# Closing Phase 7

Written 2026-10-18, 18:36 UTC, for the operator, to close Phase 7 today. Phase 7's operating
mode (CLAUDE.md) and its burn-down (docs/PHASE7_BURNDOWN.md) are what this closes. Times are UTC,
with MDT (UTC−6) beside where it helps.

## Where it stands

The host runs **c60a7a54** (CI #938), deployed 2026-10-18 20:16:59 UTC (ab1909d2 at 18:33:56 before it; every commit since is tests or docs, and no deploy until the operator's walk is done), its GET walk passed
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

1. **Walk P7-27** (docs/walks/P7-27.md, about 30 to 40 minutes; started 2026-10-18 at about
   21:20 UTC): 12 read-only steps, each with its PASS line; at step 12, the About screenshot it
   describes, saved as `<home>/Documents/nmas-reports/P7-27-2026-10-18/about.png`; then
   section D's six board divergences, each "keep" or "change". Paste your results.
2. **Decide C1192**: build it now, or defer it explicitly (the agent's three-line account is in
   the session).
3. **Paste the replacement** for CLAUDE.md's "Never send the operator to today's (v1) pages"
   bullet (the text is in the session).

Done since this was first written: the CLAUDE.md script ran and its lines are committed with
"Lab 7's lessons, kept" (350fd6cd); the inferences are decided (below); C1294 is built and shown
(305bdcbf).

After 1 and 2 the agent: records About (C650), closes 7.D in the writeup, closes C1267, deploys
and walks. **Phase 7 then closes**: the burn-down's last items (P7-09's 7.D, C650, P7-27) are
done, and C1192 is built or deferred by your word.

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
| C650 | **Open: Phase 7's own.** 27 screens are recorded (be578a3c added Save, pending and retired). About's record comes from your walk screenshot; then 7.D closes. |
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
| C1192 | **Open, for the operator's decision:** build now, or defer explicitly. See the three lines below. |
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
| C1260 | B | **Re-ranked C to B by the operator.** Fixed: 1b08287f. Its bound is being measured under reproduced load, at your word; 30 s holds until then. |
| C1267 | B | **Open: Phase 7's own.** P7-27 is merged (4e631168) and deployed; your walk is running now. |

### In all

- **Of the 6 A:** 1 is open for Phase 7 (C650, About). 5 are deferred by your decisions: the
  triage, and mutation parked.
- **Of the 19 B:** 3 are closed. 1 waits on your call (C1192). 12 are deferred by the triage or
  the parked mutation. 3 are deferred by the agent's placement under your D-categories (C472,
  C822, C828).
- **Since then:** 12 opened, 1 A and 11 B. 11 are closed; 1 is open (C1267, your walk).

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
