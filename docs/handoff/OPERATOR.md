# Waiting on the operator

The one queue of everything waiting on the operator (the week plan's "How a session picks its
work", rule 3). Each entry: what is asked, the options, the recommendation, the file to open; 6
lines or fewer. A session adds its question here, marks the plan item `BLOCKED →
OPERATOR.md#<anchor>`, and moves on. When the operator answers, the answer goes under the entry
and the next session unblocks the item and moves the entry to Answered.

## Open

### back-to-working

- **Where it stands (2026-11-27 19:13 UTC, 12:13 Denver), read on the hosts:**
  - **Healthy:** Mercury runs f77075d0 (the one exception deploy at 19:05Z, SMOKE OK; the
    updater's copy re-installed, its check ok). Ten of the twelve devices answer, each new SSH
    key kept under the window: r1 to r4, r6, r7, s1 to s4; their syslog reaches Loki and r1 to
    r7's telemetry streams came back by themselves. Nine of the outage's incidents closed at
    19:12:06Z on C4289's fix ("every symptom the incident named has cleared by itself"), s3's
    already at 18:33Z; no alert fires on the ten. The host's startup and heartbeat checks pass
    (C4280, C4281 closed); coverage-nightly's only red is C4090's (C4279).
  - **Not yet:** r8 and s5 (C4288). Their nodes run (up since 17:39Z, healthy) but boot
    configless, and Mercury's ZTP serves only devices still being onboarded, so starting or
    redeploying their nodes brings them back blank again: not done. Everything still open waits
    on them: r2's incident (it stands on its OSPF and OSPFv3 to r8, rightly), r8's and s5's
    incidents, the six alerts (both unreachable, no heartbeat, r8's two streams), and nine Needs
    attention rows (the r2 to r8 adjacencies, both alert groups, reachability, the startup
    check, the adjacencies not judged, r8's and s5's drift).
- **The click list, only yours:**
  1. **r8 and s5:** answer #r8-s5-configless ((a) recommended: startup files from their goldens,
     then a redeploy of those two). Why yours: it changes the lab's design for two nodes. Once
     both answer, their nine rows, three incidents and six alerts clear by themselves.
  2. **The break-glass record:** Credentials › Export (r8, s1, s5 rotated since the last
     export, 2026-11-21). Why yours: the passphrase is a person's.
  3. **"The last command_plan to r7: failed" (2026-11-17):** it clears when a later deploy or
     restore to r7 finishes clean; r7's streams are back. Why yours: r7's collector case is the
     one you kept for the AI's first live press; say if a plain restore of r7 should clear it.
  4. **"No stored baseline can be re-applied":** Save All, once r8 and s5 answer. Why yours: it
     writes every device's startup, s3 included, and the agent never touches s3.
  - **Clears by itself:** "Self-healing did not scan configuration changes on Default from
    2026-11-26T06:29:51Z to 2026-11-26T18:30:42Z" goes at 2026-11-28 18:30Z (detection reads
    again normally; the span is the outage, when no device could log; why its cursor stood
    still is C4292, UNKNOWN).

### outage-cleanup

- **Triaged (2026-11-27 18:15 UTC, read-only):** the 12 open incidents are one per device, opened
  2026-11-25 03:26 to 03:30 by the outage (each: heartbeat missing, SNMP unreachable; r1 to r4
  and r6 to r8 also telemetry streams 101 and 102 lost), all decided can't-fix by the grace
  while the devices could not be read, all standing. Some took in boot-time triggers on
  2026-11-27 (OSPF adjacencies to s3 at 17:43, r2 to r8 at 17:47, critical syslog at 17:48).

  | Incident | Device | Still true now? | What clears it |
  |---|---|---|---|
  | hi-ed08deccc3a5, hi-f7e8d3b16ffe, hi-0c9fc885c6f5 | r1, r3, r4 | no: no alert fires, streams back, every adjacency up | nothing in Mercury (C4289) |
  | hi-f19e5999288c, hi-c084ebb2fb2c | r6, r7 | no: the same | nothing in Mercury (C4289) |
  | hi-08fa12d33834, hi-e3f2c2f602ec, hi-5aa885b09b8b, hi-21b0c7199408 | s1, s2, s3, s4 | no: no alert fires; s3's adjacencies up | nothing in Mercury (C4289) |
  | hi-4eefc86ca154 | r2 | partly: r2's OSPF and OSPFv3 to r8 are down | wait for r8 |
  | hi-363505d6bd12, hi-e9e3ec028af5 | r8, s5 | yes: unreachable, no heartbeat, r8's streams | wait for r8 (#r8-s5-configless) |

  No re-subscribe is needed: r1 to r7's streams came back by themselves. **There is no click
  list:** Mercury has no action that closes a standing can't-fix, and the clean read that
  should end these (the drift run at 18:11Z read the ten at their goldens) cannot, because a
  decision taken while the device was unreadable records no departure (C4289, B). Off closes
  nothing (C3880).
- **The walk:** s1's hi-08fa12d33834 would take in the walk's BPDU as one more symptom, so no
  incident of the walk's own opens: "go 1" is held until this is answered.
- **Options:** (a) the fix (a decision on an unreadable device ends at its first clean read at
  its golden; a few lines in `modules/heal/incidents.py`, its test red first) deployed as a
  one-time exception from a sha whose only red is C4090's loop scan, which the walk itself
  lands; the ten close at the next drift run (every 30 min), then the walk; (b) walk anyway
  into s1's standing incident: whether its card then offers the saved fix is not measured, and
  record 2 needs a second incident; (c) wait: nothing clears them until the fix deploys, and
  the fix waits for C4090, which waits for the walk. **Recommendation:** (a): without it the walk
  and the fix wait on each other. It needs your word because main is red when it deploys.
- **Answered 2026-11-27, the operator's words:** "outage-cleanup: (a). I authorise one deploy, via
  nmas-deploy using whatever flag it needs to pass a red CI (the fast-lane mode file included,
  scoped to this one deploy and deleted right after), from a sha that contains 0f7a3d70 and whose
  only red, in CI and the local full suite, is C4090's loop scan, listing exactly the two records
  the s1 walk makes. Any other red means no deploy. Record the exception in decisions and
  FAST_LANE_DEBT.md. This one deploy only; every later deploy is on fully green CI. Before it: an
  independent review of 0f7a3d70 (heal path). After it: confirm the smoke check passed and the ten
  incidents close at the next drift run, then tell me "ready for go 1"."
- **Done 2026-11-27:** the review of 0f7a3d70 found a defect (it would have closed an incident
  whose symptom still stood); fixed forward in 05965024 (a clean read re-stands it on its
  symptoms, and detect's step closes it once they read gone), and a second review found it safe
  (C4290 and C4291 recorded). f77075d0 deployed at 19:05Z, its only red in CI #2338 and the
  local full suite C4090's two-record loop scan; SMOKE OK; the mode file deleted at 19:06:21Z.
  The drift run at 19:11:52Z read the ten clean: nine closed at 19:12:06Z, s1's
  hi-08fa12d33834 among them, and r2's stands on its symptom (its OSPF to r8 is down). Moved to
  Answered at the session's end.

### r8-s5-configless

- **Asked (2026-11-27 17:55 UTC, 10:55 Denver):** after the redeploy, r8 and s5 do not answer.
  The lab boots them configless (Lab 9's design: they arrived by ZTP), and Mercury's ZTP serves a
  bootstrap only to a device pending onboarding; both were promoted long ago. r8 leased
  10.255.4.10 and asks every 5 s; the responder refuses: "no pending ZTP device holds the
  reservation … (promoted, abandoned, or never onboarded as ztp)"; s5's reservation is gone
  ("holds no reservation the tool wrote"). The other ten answer (C4288).
- **Options:** (a) give both startup files from their goldens, as the other ten have: add r8 and
  s5 to the lab's map so the startup sync builds them, set their startup files in the topology,
  and redeploy (the one command, its window first); (b) retire both and onboard them again by ZTP,
  as Lab 9 first did (their history archived, two onboardings you approve); (c) leave them down
  until something needs them. **Recommendation:** (a): every node then comes back from a redeploy
  by itself, and Lab 9's ZTP pass stays recorded as it was. It needs your word because it
  changes the lab's design for two nodes.
- **Answered 2026-11-27, the operator's words:** "Convert r8's and s5's latest goldens to
  containerlab startup configs, the same way the other ten are made (sanitised as theirs are).
  Add startup-config lines for r8 and s5 to the topology file so every future redeploy uses
  them. Reload r8 and s5 per lab/REDEPLOY.md. Skip the drift pre-flight (they're down); open
  Mercury's window for new host keys as the runbook does. Never touch s3. … If anything fails,
  fix it forward and keep going."
- **Done 2026-11-27 (in progress at 21:15 UTC):** the lab's map maps r8 and s5 (their two
  DECLARED-UNMAPPED lines replaced by rows like r7's; the earlier map kept beside it); the
  startup sync built both from their goldens at intent, sanitised as the ten are (r8 130 lines,
  s5 104, each up-ifs-ok), copied and committed them in the lab's repository at 21:09:31Z; the
  pre-flight passed every check but the drift read on all 12. The topology's r8 block is r6's
  (startup-only launcher), s5's is s1 to s4's (stock launcher, CPU 19 kept); **its commit in the
  lab's repository is yours** (a git write on a host's checkout stays refused):
  `cd ~/labs/lab && git add rcn-lab1.clab.yml && git commit -m "lab: r8 and s5 boot from their startup files (C4288)"`.
  The one redeploy command would have recreated every node, s3 included, and containerlab
  0.79's `--reconfigure --node-filter` destroys the whole lab; a throwaway three-node lab
  measured that a plain `containerlab deploy` reconciles a running lab, recreating only a changed
  node with its links restored and its neighbours untouched. The dry run planned exactly "r8
  (config drift: Env, Binds)" and "s5 (…)"; the window (id 7764c4aff65104e1, 21:11:07 to
  22:11:07Z, new host keys) came first; the deploy at 21:11:42Z recreated r8 and s5 alone (r2 and
  s3 kept their 17:38 start), parking and restoring their links (r2's eth3 kept its peer and
  its tap redirects).

### s1-walk

**RECORD 1 CAPTURED; READY FOR THE REWRITTEN SHEET (2026-11-27 21:43 UTC, 14:43 Denver).** Go 1
ran at 21:36:26Z: incident hi-f90c700a7d45 opened at 21:36:41Z and your press of BPDU guard
recovery (access ports) fixed it, verified, at 21:40:05Z. Its proof is a command plan's run
(`script-bpdu-guard-recovery-access-ports`) with 2 checks and 4 reads, captured masked
(record 1, `P.reads`, kept outside the repository until C4090 lands). The old step 3 could not
work: the card's save offer takes only a catalog command plan's run, never a saved fix's ("no
command plan ran and passed its own verify", words that are wrong for this case: registered).
So record 2 is made by **Fixes › New fix…** instead, saved **Manual**, which the card offers
beside the Automatic one; your later instruction to set "any port" to manual is then met from
the start. s1 has no open incident; Gi1/0 is back up. Only the rewritten steps below remain.

**Record 2's steps (about 10 min):**

1. **Troubleshooting › Fixes › New fix….** Name: **BPDU guard recovery (any port)**. What it
   fixes: **err-disabled**, cause **BPDU guard**, port role **left unset (any)**, **the cause has
   cleared** ticked. Lines: the three it offers, **`interface {interface}`, `shutdown`,
   `no shutdown`**. Checks before: **The port is err-disabled by the cause now**, **The switch does
   not recover the cause itself**, **The cause has cleared**. Verifies after: **The port reads
   connected**, **No new err-disable**. (These are the access-ports fix's own, read from it; only
   the port role differs.) Read its preview on the example, then **Save as Manual only**.
2. **"go 2".** Wait for the agent's "incident 2 open".
3. Open the new incident. The card offers **Fix with saved script: BPDU guard recovery (access
   ports)** and, beside it, **Fix with saved script: BPDU guard recovery (any port)**: that pair
   is record 2. **Write "hold" in chat and wait** for the agent's "captured" before pressing.
4. Press either one. Wait for Fixed. The walk is done; the agent lands C4090.

**If something differs:** New fix… refuses the draft, or the card offers one fix, not two: write
what it says in chat and stop; nothing is retried.

**Superseded below: the first sheet (go 1 done, its step 3 impossible).**

**READY FOR GO 1 (2026-11-27 19:13 UTC, 12:13 Denver):** s1's outage incident hi-08fa12d33834
is closed, not re-stood (19:12:06Z: "nothing to heal: every symptom the incident named has
cleared by itself ... s1 is at its golden"); s1 has no open incident, no alert fires on it,
Grafana's window silence ended 18:13:33Z, and Mercury runs f77075d0. Write "go 1" in chat when
you start; the agent sends no frame before it.

**Re-checked against the lab as it is now (2026-11-27, 17:45 to 17:55 UTC), after the redeploy
(#lab-down, Answered):** s1 runs and answers Mercury (its new SSH key kept under the window,
17:49Z), and boots its golden at intent, whose Gi1/0 has `spanning-tree bpduguard enable`
(access VLAN 10, portfast edge; read masked); its syslog reaches Loki again; h1 kept its MAC
(aa:c1:ab:99:f6:e2, so the frame is unchanged), has socat, leased 10.10.10.100 and reaches s1's
VLAN 10 address; the saved fix **BPDU guard recovery (access ports)** is held for Default
(Automatic); Default's self-healing is in Dry run. The window's Grafana silence on s1 ends
18:13:33 UTC (11:13 Denver): the walk starts after it. s1's outage incident (hi-08fa12d33834,
no heartbeat and SNMP unreachable while it was down) must close first, or the BPDU folds into it
instead of opening its own; the agent says in chat when it has, and the walk is ready then.

**The s1 walk for C4090's records (about 15 min, tonight).** Two of the three missing records
come from it: `P.reads` (a Fixed incident whose proof is a command-plan run with its reads) and
`F.more` (an open incident with two Automatic saved fixes matching it). Default's self-healing
is in Dry run (read 2026-11-25 16:45 Denver), so no saved fix runs by itself: each runs only on
your press. Never s3; not between 02:30 and 03:30 Denver.

**The cause (the agent's, on the lab host):** one crafted BPDU from h1 into s1 Gi1/0, which BPDU
guard err-disables (the Lab 10 demo's frame, its before/after checks). The agent sends it when
you write "go 1" or "go 2" in chat, and says when Mercury has opened the incident (about 1 to 2
min: the alert, then the incident).

1. **"go 1".** Wait for the agent's "incident 1 open".
2. Open Incidents, then the new incident "s1 Gi1/0 err-disabled by BPDU guard". The card offers
   **Fix with saved script: BPDU guard recovery (access ports)**. Press it. Wait for the card to
   say Fixed (its run's verify takes about 30 s to 1 min). This is record 1: the agent captures it
   (the run's proof, "show proof", with its reads).
3. On the same card, **Save this fix so Mercury handles it automatically?** is offered. Open
   **Customize…**, untick **port role**, set the name to **BPDU guard recovery (any port)**, and
   press **Save**. It is saved Automatic (saving is the approval); the line above Save says what
   it runs on now (it should say no other open incident).
4. **"go 2".** Wait for the agent's "incident 2 open".
5. Open the new incident. The card offers **Fix with saved script: BPDU guard recovery (access
   ports)** and, beside it, **Fix with saved script: BPDU guard recovery (any port)**: the second
   is record 2. **Write "hold" in chat and wait** for the agent's "captured" before pressing.
6. Press either one. Wait for Fixed. The walk is done; the agent captures the last record and lands
   C4090.

**If something differs:** the card offers no saved script (the match did not hold), or a press is
refused: write what the card says in chat and stop; nothing is retried.

**The third record cannot be made by any walk, and needs your word:** `P.net_zero.lines` draws the
lines a command plan's run changed, inside a Fixed incident's proof. A run whose configuration
after differs from before is rolled back and refused (`command_plan_run`'s net-zero check), so no
Fixed proof ever holds such lines. **Options:** (a) your words to declare that loop in
`EMPTY_IN_FIXTURE` with that reason (a Test-Weakened trailer and its row); (b) remove the loop
from `_inc_proof.html` (the words stay, the lines go; a board record compared again).
**Recommendation:** (a): the card keeps drawing the lines if a future runner ever keeps a
differing run.
**Answered 2026-11-27, the operator's words:** "s1-walk third record: (b). Remove the
P.net_zero.lines loop from _inc_proof.html (keep the words), and compare the board record
again. No EMPTY_IN_FIXTURE entry for it. After the walk, once both records are captured, change
"BPDU guard recovery (any port)" from Automatic to manual. An err-disable on an uplink is a loop
or a rogue switch and must never be re-enabled automatically. Note it in decisions." The loop
removed (the words kept) and docs/fidelity/incident.md compared again, 2026-11-27.

### assistant-v6-cases

- **Asked (2026-11-28 06:3x UTC, 23:3x Denver):** the assistant's prompt v6 (a change as a plan,
  "no tool", reads of named devices) is deployed but unmeasured (C4333): its 39 recorded cases
  ran on v2 to v4, and none is a change or a no-tool question. Measuring it spends provider money.
- **Options:** (a) record about 8 new cases (4 changes, 2 no-tool, 2 named-device reads), then run
  all 47 ten times on Haiku 5.5 at the batch rate with `scripts/nmas-assistant-cases`: about $1
  (47 x 10 x about $0.0015, from the panel's measured $0.0031 a call at half price), inside the day
  cap; (b) the same once more on Sonnet 5.5, about 20 times that; (c) not now: the label stays
  Advisory (beta). **Recommendation:** (a); (b) only if Haiku misses the 95% floor.

### automatic-port-scope

- **Asked (2026-11-28 00:25 UTC, 17:25 Denver):** your access-only rule is built for err-disable
  fixes (C4312). The review of it found that saved fixes for Mercury's other port conditions (a
  port bounce for a stuck port, a flapping port, an interface shut, a link down) carry no port
  role, so the rule does not see them: such a fix could be made Automatic and run on a trunk or
  uplink port. That was so before the rule, and Default holds no such fix (C4320).
- **Options:** (a) the rule covers every port condition: each stays Manual until Mercury's
  classifier for it names the port's role, then only access may be Automatic, as for err-disable;
  (b) err-disable only, as built. **Recommendation:** (a): the same reason holds (an uplink
  acted on by itself), and it is the same one rule.

### automatic-port-roles

- **Asked (2026-11-27 23:56 UTC, 16:56 Denver):** the fix-choice change makes a saved fix whose
  match leaves the port role UNSET (any port) never Automatic, by every path, as you ordered. The
  second independent review found that a fix whose match names `port_role: trunk` can still be
  Automatic: a fix saved from a trunk port's err-disable keeps the problem's role, and would
  re-enable every trunk (uplink) err-disable by itself, against your reason ("An err-disable on an
  uplink is a loop or a rogue switch and must never be re-enabled automatically"). Default holds
  no trunk fix today (C4312).
- **Options:** (a) only an access-port match (`port_role: access`) may be Automatic: any-port and
  trunk both refused, by the same one guard every path passes; (b) keep the rule as written
  (only an unset role refused), trunk fixes allowed Automatic.
  **Recommendation:** (a): it is what your reason says, and it is one line in the guard.
- **Answered 2026-11-28, the operator's words:** "automatic-port-roles (C4312): Automatic only for
  access-port fixes. Write it as an allowlist: access may be Automatic; trunk, routed, unset and
  any unrecognised role are always Manual. One rule in the single guard. Also fix C4311 now: any
  stored fix the guard would refuse as Automatic is converted to Manual and shown as Manual. Both
  may go in a follow-up commit after d703d3580 deploys."

### ci-ten-gate-memory

- **Asked (2026-11-25):** the ten shards alone at 2 workers (`memory.peak`, each in its own scope,
  2026-11-25 23:50 to 00:28 UTC): browser1 2.21, browser2 2.45, browser3 1.94, a 2.30, b 1.93,
  c 2.05, d 3.87, e 1.78, f 4.40, g 4.09 GiB, 27.0 in all (the five's was 18.5); their tests
  total 32,644, the full suite's. Your words cover SHARDS, BROWSER_SHARDS and WAVES only, and
  that is not enough: two waves cannot fit the 11.1 GiB cap (about 13.5 each), and all at once
  the gate would give each of the ten shards 2 workers (`nmas-workers` GATE_PEAK, measured for
  five), about 27 GiB.
- **Options:** (a) your words for three waves of about 8 to 10 GiB at 2 workers (f, browser2,
  b · g, a, e · d, browser1, browser3, c) under today's cap, the gate's "in two waves" words
  counting the waves, and all ten at once only at 1 worker a shard until a ten-shard gate is
  measured (nmas-workers' GATE_PEAK); (b) CI ten and the gate five, dropping C349's parity;
  (c) CI stays at five. **Recommendation:** (a). The edits wait as `~/mercury-runs/ci-ten-shards.patch`.
- **Answered 2026-11-27, the operator's words (for the commit's Approved-By):** "ci-ten-gate-memory: (a). I authorise changing scripts/nmas-gate and scripts/nmas-workers for ten shards: three waves of about 8 to 10 GiB at 2 workers a shard under today's memory cap, the gate's wave words counting the waves, and all ten at once only at 1 worker a shard until a ten-shard gate peak is measured. No other change to either file." Moved to Answered once landed.

### ratchet-no-screen

- **Asked (2026-11-25):** Settings' search names the settings no screen sets
  (`modules/settings_index.py` `NO_SCREEN`): four by design, two gaps (C4266). Its test pins the
  two gaps exactly, so a third cannot join without editing that test (5de31cb9). Declaring
  `NO_SCREEN` a ratchet ("shrinks") is a line in tests/ratchet_lists.py, which needs your words.
  **Options:** (a) your words for that one RATCHETS line; (b) leave the test's exact set as the
  guard. **Recommendation:** (a), so the weakening check refuses a new gap on its own.
- **Answered 2026-11-27, the operator's words (for the commit's Approved-By):** "ratchet-no-screen: (a). I authorise adding one RATCHETS line to tests/ratchet_lists.py declaring modules/settings_index.py's NO_SCREEN a shrinking list. No other change to that file." Moved to Answered once landed.

## Answered

### claude-md-ten-shards

- **Asked (2026-11-27):** the gate now runs ten shards (your ci-ten-gate-memory words), so
  CLAUDE.md's "When the laptop's free memory…" rule names the five shards and two waves. In it,
  replace

  ```
  from 18.5 GiB the gate runs its five shards
    at once, from 11.7 GiB in two waves capped at 10.7 GiB (browser1, browser2, a; then browser3,
    b; a failed wave stops the next)
  ```

  with

  ```
  from 29.0 GiB the gate runs its ten shards
    at once at 1 worker each (the operator, 2026-11-27, until a ten-shard peak is measured),
    from 11.7 GiB in three waves capped at 11.1 GiB (f, browser2, b; then g, a, e; then d,
    browser1, browser3, c; a failed wave stops the next)
  ```

  (checked: tests/test_claude_md.py's `unenforced` finds none, before and after). After you
  paste, the agent commits CLAUDE.md as you left it.
- **Answered 2026-11-28:** the operator pasted it; tests/test_claude_md.py passes (61, with
  tests/test_claude_md_edit_hook.py); committed as the operator left it.

### claude-md-0230

- **Asked:** CLAUDE.md is yours (the `claude-no-claude-md-edits` hook refuses the agent's edits), so
  the 02:30 rule waits for you to paste it. Put these lines first under "### Working method"
  (checked: tests/test_claude_md.py's `unenforced` finds none unenforced, its paths exist):

  ```
  - **Sessions run until 02:30 Denver (the operator, 2026-11-24): never end a turn before 02:30
    America/Denver, and never stop to report, summarise or ask. Progress goes in the day's
    report file; a question goes in docs/handoff/OPERATOR.md, its plan item marked BLOCKED, and
    the next item is taken. At 02:30 stop at a clean point, update docs/handoff/latest.md and the
    day's report as the morning session's handoff, then end the turn. Cost: no progress shown in
    chat until the handoff. Prevents: work stopping for a report, or for an answer nobody is
    there to give.** [not mechanised]
  ```
- **Also:** the fast lane is retired (2026-11-24), so the two rules "Temporary fast lane" and
  "Temporary skip mode within the fast lane" under "### Git, the gate and deploys" are stale: delete
  them both. After you paste, the agent commits CLAUDE.md as you left it.
- **Answered 2026-11-28:** the operator pasted the 02:30 rule first under Working method and
  deleted both fast-lane rules; tests/test_claude_md.py passes; committed as the operator left
  it. No other rule in CLAUDE.md names the fast lane or its skip mode (searched: "fast lane",
  "fast-lane", "skip mode", "debt", "full pass", "rehearsed build", "Lab 10 demo").

### lab-down

- **Asked (2026-11-26 06:55 UTC, 23:55 Denver):** the lab's routers and switches had not run
  since 2026-11-25 03:25 UTC (C4282); lab/REDEPLOY.md's pre-flight said "0 of 12 pass" (each
  "the last drift run did not read it"), so the agent did not redeploy. Options: (a) your word to
  redeploy, setting aside the drift condition for this one start; (b) you bring it back; (c)
  leave it down. Recommendation (a).
- **Answered 2026-11-27, the operator's words:** "lab-down: (a). I allow one lab redeploy that
  skips the pre-flight drift check. The nodes are down, so nothing on them can drift. Every other
  pre-flight check still applies. Record it in decisions." Then: redeploy and confirm r1–r8 and
  s1–s5 answer; find the reboot's cause read-only (if automatic, the one-line change here); a C
  row for nodes not coming back after a host reboot (C4287); re-check the s1 walk sheet and say
  it is ready, then carry on with Stage 5; after the walk, capture masked, land C4090, and deploy
  on a fully green CI, that deploy first over everything else.
- **Done 2026-11-27:** the pre-flight read at 17:37 UTC: every other check passed on all 12
  (credentials current, golden after its last rotation, 0 newer goldens, everything Mercury needs
  carried); the window recorded 17:38:38Z (id 6f91922a67e3214e, 90 minutes, new host keys);
  `containerlab deploy -t rcn-lab1.clab.yml --reconfigure` exited 0 by 17:39 UTC. Ten of the
  twelve answer, each one's new SSH key kept under the window (17:44 to 17:49Z, none refused):
  r1 to r4, r6, r7, s1 to s4. r8 and s5 do not (#r8-s5-configless). The window was ended early
  at 17:54:33Z, as the runbook ends it once its devices have answered, so it covers nothing more;
  Grafana's silence now ends 18:13:33Z. Its "new host keys accepted" row on Needs attention is
  yours to review in History and acknowledge.
- **The cause:** not an automatic reboot. The hypervisor itself stopped uncleanly (its journal
  ends 2026-11-24 19:52:34 MST with no shutdown; it booted again at 20:25:14 MST and its start-all
  started the lab host and the NMAS host). The lab host's unattended upgrades have
  Automatic-Reboot off (the default; the line is commented out); the new kernel it booted
  (6.8.0-149) had been installed earlier and was waiting for a reboot, and 6.8.0-151, installed
  at 06:44 UTC after the boot, waits for one now. So there is no line to change on the lab host. Why the
  hypervisor stopped is not in its logs (no error before the end): a power cut or a hang, which
  only you can tell from the machine itself.

### c4075-smoke

- **Asked (2026-11-25):** your ruling 8 has the deploy's smoke pass `--expect-local-account-off`,
  but `nmas-deploy` runs its smoke only on a fast-lane deploy, and the fast lane is retired. A
  `--wait` deploy runs no smoke of its own. **Options:** (a) `--wait` runs the smoke with the
  flag and reverts on red, as the fast lane did; (b) keep the hand-run check after a deploy.
  **Recommendation:** (a). It needs your words, because it changes how every deploy ends.
  File: C4075's row, docs/OPEN_FINDINGS.md.
- **Answered 2026-11-25 (16:37 Denver), the operator's words (for the commit's Approved-By):** "c4075-smoke: (a). I authorise changing scripts/nmas-deploy so that a --wait deploy runs the smoke check with --expect-local-account-off and reverts the deploy if it's red. No other change to nmas-deploy."

### gui-direction

- **Asked:** which GUI direction to build (the week plan's one big decision). Three drawn on the
  same six screens: A Workbench (list and detail), B Inbox (triage first), C Document (one
  readable page per object). Open `design/proposals/README.md` (the comparison), or the zip
  `design/proposals.zip` (mockups, shots at both sizes, the research and inventories).
- **Options:** A, B, C, or C with B's Needs attention queue and step timeline.
- **Recommendation:** C with B's queue and timeline (about 30 build days by its estimate).
- **Answered 2026-11-25 (16:37 Denver), the operator's words:** "gui-direction: C with B's Needs attention queue and step timeline. One change: the assistant is a side panel the page reflows around, not a drawer over a dimmed page. Build order, each step deployed when green: 1. the shared frame (layout, type, the side panel mount, the timeline component); 2. Settings; 3. home and Needs attention, with B's queue; 4. the incident page; 5. the device page; 6. the rest. Steps 1–5 by Nov 30 where you can. Add these to the week plan's Stage 5 in this order, ahead of Stage 6." Written into docs/plan/week-2026-11-23.md's Stage 5.

### c4135-age

- **Asked (2026-11-24):** C4135 (B, Lab 9: blocks): Analyse this network reads the latest kept
  snapshot whatever its age (one 9 days old on 2026-11-20); the bar shows "collected <time>" but
  never says it is old. The row leaves the age to you. **Options:** (a) older than the
  collection's own bound × 2.5 (measured: the agent proposes the number); (b) 1 hour; (c) 24 hours.
  Past it, the card says "collected N days ago: Collect now first" and Analyse offers Collect now.
  **Recommendation:** (b). File: templates/v2/_sdn_analyse.html, modules/sdn/analyst.py.
- **Answered 2026-11-25 (16:37 Denver), the operator's words:** "c4135-age: (b), 1 hour."

### c2518-runner

- **Asked (2026-11-24):** C2518 (A) layer 1, the local CI runner: act given no Docker socket
  (`--container-daemon-socket -`), empty `--env-file`/`--secret-file`/`--var-file`, and started in an
  empty folder so no `.actrc` from the commit is read. Built as `~/mercury-runs/c2518-runner.patch`
  (scripts/nmas-local-ci, 53 lines, not committed). scripts/nmas-local-ci is a guard path
  (scripts/nmas-guard-check, WHOLE), and the row holds your 2026-11-05 design only in paraphrase.
  **Options:** (a) your words for this change, quoted in its Approved-By; (b) leave it until layer 2.
  **Recommendation:** (a); the timer stays off either way.
- **Answered 2026-11-25 (16:37 Denver), the operator's words (for the commit's Approved-By):** "c2518-runner: (a). I authorise ~/mercury-runs/c2518-runner.patch's change to scripts/nmas-local-ci: no Docker socket, empty env, secret and var files, started in an empty folder. No other change. The timer stays off."

### ci-shards-gate

- **Asked (2026-11-24):** your 10-shard words cover ci.yml and scripts/nmas-shards, but the gate
  runs CI's shards argument for argument (C349): tests/test_nmas_gate.py holds
  `nmas-shards.matrix(...) == nmas-gate.SHARDS`, so ten shards also changes scripts/nmas-gate
  (`SHARDS`, `BROWSER_SHARDS`, the memory `WAVES`), a protected guard. ci.yml itself needs no
  edit (its matrix is nmas-shards' output; `-n auto` is already 4 on a 4-core runner).
  **Options:** (a) your words for nmas-gate's shard constants and waves too; (b) CI's ten split
  from the gate's five, which drops C349's parity (a guard test changed: your words as well).
  **Recommendation:** (a).
- **Answered 2026-11-25 (16:37 Denver), the operator's words (for the commit's Approved-By):** "ci-shards-gate: (a). I authorise changing scripts/nmas-gate's SHARDS, BROWSER_SHARDS and memory WAVES to match ten CI shards, keeping C349's parity. No other change to nmas-gate."

### c4090-confirms

- **Asked (2026-11-24):** C4090's records need two confirms only a verified person can give:
  a command plan's run approved by hash (its Fixed run with a net-zero difference and its reads),
  and two saved fixes matching one incident. The host takes identity only from the access
  proxy's assertion (no local exemption), and a confirm is a person's decision (CLAUDE.md), so
  the agent cannot press them. **Options:** (a) the agent writes a walk sheet for s1 (cause, the
  clicks, about 10 min), you press the confirms, the agent captures masked and lands C4090;
  (b) another way you name. **Recommendation:** (a). Meanwhile the agent does the CI shards.
- **Answered 2026-11-25 (16:37 Denver), the operator's words:** "c4090-confirms and c4090-records: (a). Write the s1 walk sheet in OPERATOR.md now (cause, the exact clicks, what to wait for, about 10 min). I'll press the confirms tonight. Then capture masked, land C4090, and deploy on a fully green CI." The sheet is below, under Open, as `s1-walk`.

### c4090-records

- **Asked:** C4090's three loops are the last red once the patches land (stacked suite, 2026-11-24);
  they need records no store holds (a Fixed command-plan run with a net-zero difference and its
  reads; two saved fixes matching one incident), and your ruling says real captures only.
- **Options:** (a) wait for them to occur; (b) the agent makes them on the sandbox device through
  Mercury, then captures them masked; (c) your words for EMPTY_IN_FIXTURE.
- **Recommendation:** (b), outside the backup window, never on s3. File: C4090's row, docs/OPEN_FINDINGS.md.
- **Answered 2026-11-25 (16:37 Denver):** with c4090-confirms, the same words ("c4090-confirms and c4090-records: (a)"): the records are made by the operator's walk on s1 (the sheet, `s1-walk`) and captured masked, which is this entry's option (b) in effect; s1 is the sandbox device, never s3.

### session-namespace

- **2026-11-24:** no longer blocking. The operator retired the overnight loop,
  and a session from VS Code (whose label makes the namespace) landed every waiting patch,
  eac546ae to d030f04a, the hook's red-green run on each. Its option (a), the AppArmor profile,
  stays open only if a session outside VS Code is wanted again.

- **2026-11-23, loop-script:** the script arrived (3f9c6b0d) and the crontab runs it at 03:35.

- **2026-11-23 (evening), rulings on overnight/gui's standing failures** (the plan's Stage 1
  items): C3970 and test_heal_analysis_never_read fixed (cfe043d8, bd09416f); C3886, C4090,
  C4206, C4207 and C4208 as recorded in `docs/handoff/rulings-overnight-gui.md`, carried out by
  Stage 1.
