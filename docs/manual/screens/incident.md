# An incident's page

Each self-healing incident has a page of its own, at `/v2/incident/<its id>`. It leads with
its bottom line: three plain lines saying what happened, what it costs the network or Mercury,
and how to fix it, with the one thing to press ([The bottom line](#bluf)). Under it, one card,
[Fixing it](#ai-troubleshooting), says where the fix stands. Everything else (the times, the
timeline, what Mercury read and did, the evidence and the record) is collapsed below: open a
part to read it. The page says one state, the same in its header and in every part. Opening
the page starts nothing and changes nothing: only a person's press does. How each time is
found is on [An incident's timeline and its time to repair](incident-timeline).

**How to open it.** One place per incident, from wherever it is named:

- on [Incidents](incidents), under Troubleshooting in the sidebar, the incident's own home:
  select its title on the **Open** or **Closed** tab. The page's breadcrumb leads back there,
  **Incidents**, then the tab the incident is on;
- on [Needs attention](needs-attention), open an item about one incident (a self-healing
  item, or a lost telemetry stream whose device's network holds an open incident for it):
  **Open the incident** is the first link in the opened item, and the item's own bottom line
  follows it;
- on [History](history), or a device's History tab, open a self-healing row: **Open the
  incident** is beside **Open the card**.

The address can be kept and shared; it stays the incident's for as long as its record is kept.

Only self-healing incidents (an id that begins `hi-`) have a page yet. An alert incident and an
SDN incident are on [Needs attention](needs-attention) until theirs are built.

## At a glance {#at-a-glance}

The top of the page tells the incident's story before any detail:

- **The lifecycle bar:** eight stages, Detected, Self-heal tried, Diagnosing, Fix proposed,
  Approved, Applying, Verifying and Healed, each with the time its own record gives. The stage
  the incident is at now is marked; one it skipped (a self-heal that needed no AI skips
  Diagnosing, Fix proposed and Approved) is drawn faint, and a failed verify is drawn red,
  never Healed.
- **Summary:** four lines. What happened; the likely cause (the AI's first hypothesis,
  "Inconclusive" with its reason when the AI ended without a fix, or else the kind of what
  opened the incident, such as a configuration change from outside Mercury); the evidence, four lines
  each opening to its raw text, with the rest counted; and what to do next. The next step is
  said here only: the incident's card below holds its action, not the sentence again.
- **Hypotheses:** what the AI considered, the one its plan acts on first, each with what it
  cites and the read that would confirm it.
- **The right rail:** confidence, severity and risk, which Mercury does not record yet (each
  says what it needs), and the AI call: its model, prompt, tokens, cost and latency, from the
  record of AI calls, with a link to History.

## The header {#header}

The title is the problem, in plain words, at most 70 characters on one line, and it is the same
words as the bottom line's **What happened**: the device, then what is wrong with what on it
("edge-b: telemetry streams 101 and 102 lost"), the change when a decision named one
("edge-b: static route added outside Mercury"), or the problem's own words for its kind
("edge-b: its configuration was changed outside Mercury"; an alert Mercury has not classified
yet says so, never the alert's rule). The alerts and log lines are its evidence, never its
title. It never quotes a configuration line, a log's code or an id: the line itself is under
[What's wrong](#whats-wrong). Once the incident is resolved the title says
how it ended: "and Mercury put it back", "put back by" the person who approved the fix, or "and
it cleared"; a close on a verified run of an AI plan or a saved fix adds nothing to the title,
since the card says who fixed it. The same title is the last step of the breadcrumb above it (after **Incidents**
and **Open** or **Closed**), cut with "…" where the row is narrow (hover over it for the
whole), and it is each row's title on [Incidents](incidents) and leads the incident's line on Needs
attention and on History, and the email that tells the team. Under it:

- **The state**, said once for the whole page ([One state](#one-state)). **Open**: Mercury is
  watching it, or a fix a person approved is running or has passed its verify. **Mercury
  working**: a heal, a saved fix or the AI's investigation runs on it now, whatever it said
  before (a dry run's would-heal, a hold), so nobody is needed. **Needs a person**: it stands
  on a decision only a person can act on, a proposed fix waits, a fix was applied and its
  verify failed, a fix a person ran stopped without fixing it, or its telemetry stream is lost
  (that fix changes the device's configuration, so a person approves it). **Fixed**: a fix was
  applied and its verify passed. **Cleared**: it closed with no fix recorded. **Cancelled**: a
  person declined the fix proposed, and what it would have fixed has since gone (until then
  the declined incident stays open and needs a person). An incident its record closed on a
  heal that did not heal, before only a healed heal closed an incident, with nothing confirming
  the fix since, reads **Needs a person**: an incident closes only on a healed outcome
  ([Confirm first](heal#confirm)); never Fixed.
- **Drill**, beside the state, when the incident opened inside a declared fault drill
  ([Declare a fault drill](fault-drill)): hover over it for the drill's id (`fd-…`), who
  declared it and the fault it expected. A drill is never drawn as a real incident; its
  figures are counted as a drill's. The same tag is beside **Open the incident** on its Needs
  attention item.
- **The level** its Needs attention item has or had (Critical or Warning), or **No person
  needed** for an incident that never needed one. A page that says Needs a person never says
  No person needed.
- **The device**, a link to its page, with the network and how many devices were attached to
  the incident; and, once it is resolved, its span: from when it was detected to when it ended.
  A fixed incident ends when its fix is verified
  ([When it ended](incident-timeline#when-it-ended)).

Every time is drawn in your own time zone; hover over one for its UTC time. People are named
by their display name.

## The bottom line {#bluf}

Three lines, at the top of the page, before anything else:

1. **What happened**: the problem, in an engineer's words ("edge1: telemetry streams 101 and
   102 lost"), never the alert that raised it nor Mercury's codes: the page's title, word for
   word. The alerts and log lines it was classified from are its [evidence](#evidence),
   collapsed under the bottom line.
2. **Impact**: what it costs the network or Mercury ("Mercury can't see edge1's interfaces or
   CPU; traffic is unaffected"). It comes from Mercury's own table for each kind of problem,
   never from the AI; a problem the table does not hold says the impact is not known.
3. **How to fix it**: the one next action, as a button. Which one:

| Where the incident stands | The next action |
|---|---|
| A saved fix's match holds for the incident's problem (an Automatic one first) | **Fix with saved script: <fix>**, run once as you (below), with **What this fix does**, its page on [Fixes](fixes); each other matching fix is its own button beside it. While a guard holds the incident it reads **Fix now with saved script <fix>** |
| The AI proposes a plan | **Approve**, **Modify…** and **Deny…** (below) |
| Mercury's fix failed, and the AI was not started by itself (its background feature was off for the network then, or the fix failed before it was turned on) | **Start AI troubleshooting**: one investigation, its cost beside it |
| You denied the AI's plan | **Ask the AI again**: a new investigation, told what you denied and why |
| The AI proposed no plan, naming a read that would settle it but that its reads do not offer | **Run <read> in Show commands**: it opens [Show commands](show-commands) on the incident's device with the command filled in, and nothing is read until you press Run there; **Ask the AI again** is beside it |
| The AI proposed no plan and named no read it lacked | **Ask the AI again** while it is offered, else **Hand over…**: never nothing |
| A cap would be passed, or nothing else is left | **Hand over…** |
| The incident's own Needs attention item offers an action | that action ([What to do](#what-to-do)) |
| Mercury or an approved plan is working, a fix's run passed its verify, or nobody is needed | nothing to press, said |

**Nothing that already failed in this incident is offered as its next action.** A fix tried
here that did not fix it is listed under Fixing it's **Attempts**, with its record, and under
**Other actions**, never as the button. **Hand over…** is beside every next action while the
incident is open, as a link: it opens its modal over the page ([Hand over](fixit-troubleshoot#hand-over)).

**Fix with saved script: <fix>** runs that saved fix once, as the verified person who pressed,
bound to the hash its preview drew from the incident's own values, with no AI: the runner holds
the device, reads its checks again, sends, verifies (rolling back a failed verify) and records,
as a job under **In progress**. A verified run closes the incident Fixed, unless the run fixed
one port and the incident holds more than that port's events ([Self-healing](heal#detect),
step 8). A press refused says why in place, naming what it compared.

**Approve** runs the plan exactly as drawn, held to the plan's hash: a step that moved since it
was drawn is refused, naming what moved. Everything that hash binds is drawn before you press:
open the plan's **What its hash binds** for the incident, the proposal, each step's operation,
its parameters and its own hash. A step that closes the collector's stale session binds that
session too: Mercury read it when the plan was proposed (the close helper's dry run, which
closes nothing, inside the job that made the proposal) and kept it with the plan, and it is
drawn beside Approve from that record, both ends and ports and how long the session was quiet,
so the page never waits on it. Approve reads it again when you press and is refused, naming
both sessions and when the plan read its own, if the collector holds another by then; nothing
runs, and Ask the AI again gets a plan that reads it afresh. A plan whose read named no session
cannot be approved, and says why. **Modify…** opens a box for what should change; the AI
returns a revised plan with a new hash, nothing runs, and Approve, Modify… and Deny… come back
with it (**Revise the plan** sends it; **Cancel** or Escape closes the box with nothing sent).
**Deny…** records your reason, which is optional (**Deny the plan**; **Keep the plan** closes it
with nothing recorded); nothing runs, and the incident stays open with **Ask the AI again** and
**Hand over…**. A step refused at its preflight is drawn refused, with why, and Approve is then
not offered: Modify… and Deny… are. Each button is busy on itself until its answer comes, and
the answer is drawn under the buttons, in place.

## Fixing it {#ai-troubleshooting}

What to do and AI troubleshooting are this one card, under the bottom line. It starts with one
status line: the incident's best current knowledge, never merely its latest event, in one
sentence. A fix available comes first ("A saved script can fix this: <fix>.", "The AI's plan is
ready."); then the AI's latest finding, in an engineer's words with an **AI** label beside it
(never "The AI found:" inside it), Mercury's note in the same sentence where its catalogue has
a step the AI did not try ("…; Mercury notes errdisable-recover (Recover an err-disabled
interface) exists and is not yet tried here."); and a failed attempt only when nothing else
is known. A press that never reached the AI (refused before any call) is never the line. While
it needs a person, the line is why, beside its one action (the same reasons the
[Incidents](incidents#row) row gives). While Mercury works on it, the line says what it is
doing now with a spinner, its live step moving as the run records it, while the header says
**Mercury working**: a heal's ("Self-healing: restoring <device> · Apply"), a saved fix's
("Self-healing: fixing with saved script <fix> · verifying") or the AI's ("The AI is
investigating" and the step it is on); a plan still drawn from before is greyed and cannot be
pressed until the new answer comes.
An AI plan whose step Mercury refuses reads "<the AI's finding>; Mercury refuses its fix as
it stands: <why>." A recovery whose port tripped again says so in the run's own words ("The
device with MAC <mac> is still connected to <device> <port>. Port left err-disabled; nothing
more sent."). An AI answer a matching saved fix now overtakes is labelled "outdated: a saved
script now fixes this (<fix>)" and collapsed. Once closed by a verified run, the line says who
fixed it: "Fixed by AI: AI plan approved by <person> at <time>." or "Fixed by Mercury: saved
script: <fix>, learned from an AI fix on <device>, approved by <person> when saved."

Then the AI's plan when there is one: what the AI found, and each step with its preflight
("preflight passed", or "refused at its preflight:" and why). Beside **Approve**, and beside a
finding with no plan, **What the AI saw and said (N calls)**, closed: each of the answer's
calls in order, your message first, each call's Sent and Received read from its History record
when you open it (masked, as History draws it). While an approved plan runs, its steps are
said "step n of N" ("Sending: step 1 of 2, on <device>"; a one-step plan unnumbered), and its
Verifying stage lists its own checks with their seconds. The plan's hash and each step's are
in [The record](#the-record).

**Fixed shows its proof.** Once the incident is Fixed, the card leads with "How it was fixed:"
and who fixed it, linked to the run (and to the saved fix's page, for a saved fix), then one
closed line, "Verified: connected, no re-trip, config unchanged · show proof". Opened: each
verify check with its words and seconds, the configuration compared before and after where
the fix is net zero, and each read the fix made, with its time from the run's start and its
answer, masked, as the read engine kept it (cut at 4,000 characters, the rest on the read's own
record). For a heal, the proof is its own verify (at intent, symptom gone), and its steps after
Fixed (save to startup, commit the golden, read it again) are listed under it with their state,
live while they run; one that failed is flagged, and the incident reopens
([Self-healing](heal#outcomes)). The proof reads only what the fix already kept; it asks no
device. Below, collapsed:

- **Attempts**: each fix tried in this incident, one line each: when, the operation, who
  proposed and approved it, its outcome, its AI cost and **Open the run**.
- **What attempt <n> found**, after a fix that did not pass: one line per subscription with its
  state in words ("Subscription 101: re-subscribed; the stream did not come back"), each opening
  to its checks (the device's connection, the stream, the collector's sessions) and any flag.
- **Other actions**: a fix that failed here, with the attempt it failed in and **Open its
  record**.
- **Holds and guards**: a guard or a hold that worked as designed, one plain line each, never
  drawn as a failure ("Self-healing won't write to edge1 until its saved config matches intent (2
  lines differ). This doesn't block the fix below.").
- **Why the AI proposes this**: what it said was wrong, its hypotheses with what each cites, its
  calls and cost, and **Was this right?**.
- **Costs**: this incident's AI spend against its cap, today's against the day cap, and what one
  investigation costs.
- **The AI's analysis**, for a can't-fix: the analysis kept for the incident, in full,
  advisory (self-healing never reads it).

When the AI cannot start because a cap would be passed, the card says which cap, and **Hand
over…** is the next action. **When Mercury's fix fails, the AI troubleshoots by itself** where
the background feature "Start AI troubleshooting automatically when Mercury's fix fails" is on
for the network: Settings › AI, beside the other background features, off by default on every
network and turned on or off only by a verified person, its estimate shown first ([AI
troubleshooting](fixit-troubleshoot#automatic)). Turning it on never catches up: an incident
whose fix failed before it was on shows **Start AI troubleshooting**. Once the incident is
resolved, the card is read-only. Each step is on [AI troubleshooting](fixit-troubleshoot).

## What to do {#what-to-do}

Where the incident's item on [Needs attention](needs-attention) offers an action and nothing
in Fixing it is the next one, the bottom line's button is that action, the same as the item's,
as the page's one primary button. The page never sends you back to Needs attention to act.

| The incident | The button |
|---|---|
| A fix waits for a person (a proposal) | **Review the fix…** opens the proposal's card under the button, with Approve and Decline ([A self-healing proposal](heal-proposal)) |
| A lost telemetry stream, nothing tried yet | **Re-subscribe <device>'s telemetry (<subscriptions>)…** opens its card under the button ([Re-subscribe a lost telemetry stream](telemetry-resubscribe)). Run from here, it is recorded as this incident's attempt. Once it has failed here it is never the button again |
| A can't-fix, or a fix whose verify failed | **Open <device>**, or **Open <device> (likely cause)** when another device's change is the likeliest cause (a hypothesis, said as one, under What's wrong) |
| A dry-run record | its question, **Right** or **Wrong…**: two answers, neither the primary |
| A run holds the device | **Open the run**: the action returns when the run ends |

The button does not move when its card appears: the card is drawn under it. Under Fixing it's
status line are what the item says to do in its own words, **Diagnose…** where the item offers
it ([Diagnose a device](diagnose)) and how its Needs attention item clears.

A page that needs nobody (resolved, Mercury working, or a fix under way) draws no primary
button. When the incident still needs a person and its item is no longer on Needs attention
(it cleared there, or a person acknowledged it), the page says so and its button opens the
device. While Needs attention is still being read, the page says that instead: an item not
read yet is never said to be absent.

## One state {#one-state}

The page's state comes from one place, and every part of the page says the same: the badge in
the header, the bottom line, Fixing it, What's wrong and What Mercury has done. It is worked
out from the incident's own records and from what was tried in Fixing it:

| The state | When | Fixing it says |
|---|---|---|
| Fixed, Cleared, Cancelled | the incident is resolved | Nothing, and why |
| Mercury working | a heal, a saved fix or the AI's investigation runs on it now, over any earlier state | What it is doing now, its live step |
| Open | Mercury is still reading the device, or its fix is running | Nothing yet |
| Open | a fix a person approved is running, or passed its verify | Nothing yet, or Nothing now: the incident closes when its symptom clears |
| Needs a person | every other case: a decision only a person can act on, a proposed fix, a failed verify, a fix that stopped without fixing it, a lost telemetry stream | It needs a person, why, and the one action above; where its fix's own stage failed, the stage under What Mercury has done says why, once, and this line links to it ("Why: the stage that failed") |

So a page never says "No person needed" or "Mercury is working on it" in one place and
"Stopped: nothing more runs unless you choose" in another.

## Timings {#timings}

Collapsed, under Fixing it; its line says the time to repair, or since when it is open.
Opened: **Detected**, **Decided**, **Fixed** and **Verified**, each from a record Mercury wrote
at the time, then **TIME TO REPAIR** in whole seconds with who it was by: "by Mercury's
self-healing · policy set by" the name of the person who confirmed the network's policy, or
"… · approved by" the person who approved the fix. A stage that has not happened reads "not
yet", and one that was never needed reads "not needed". Then one line per attempt: "applied
<time> · verified <time>", or "applied <time> · verify failed".

**A failed verify never reads Fixed.** When a fix was applied and its verify failed, the state
is Needs a person, the Fixed cell reads "not fixed", the Verified cell "failed" and when, and
TIME TO REPAIR "not repaired"; hover over a cell for why.

**Each fact is said once.** The cells and the attempt line say only the state; why a fix failed
is said once, in the stage of What Mercury has done where it failed (open the stage for the
whole of it). The timeline says each attempt's outcome ("attempt 1: rolled back").

## The timeline {#timeline}

Every recorded event of the incident, oldest first: each trigger, each device attached, each
decision, an approval or a decline, each attempt's apply and verify, and its close. It is open
on a resolved incident and collapsed on one still open.

## What's wrong {#whats-wrong}

Collapsed: open its heading to read it. What happened, as the decision stated it: the facts in
time order, then what Mercury decided to do about it. The configuration line the title names in
plain words is quoted here (a decision recorded without its facts says it as "What changed on
<device>: …"), and a likely cause on another device, said as a hypothesis. On a resolved
incident the heading reads "What's wrong (was)".

For a lost telemetry stream it leads with what its Needs attention item says: how long the
device has sent nothing to the collector and what that costs, whether the device answers
Mercury's reachability probe (a reading that cannot say is said as that, in warning colour),
and what Mercury cannot see until the stream is back.

## What Mercury has done {#what-mercury-has-done}

Collapsed: open its heading to read it. The outcome is on its heading: green for a fix that
passed, red only for one that failed; a guard or hold working as designed ("Self-healing (dry
run): held") is drawn neutral, never as a failure, its plain words on the hover ("Self-healing
won't write to edge-b until its saved config matches intent (2 lines differ)."). Then the same
five stages the heal's card on
the device's page draws: **Detected**, **Decided**, **Fixing**, **Checking** and **Done**,
each with one sentence of at most 12 words, its time and its state. Open a stage for its
steps, and for the whole of a sentence that was cut with "…". A failed stage names its step
and why, once; a later stage that failed too says only that it failed. A can't-fix is a
decision that worked: its Decided stage reads "Can't fix: needs a person", in amber, never
"failed" in red. Fixing's time is the whole fix, any wait inside its verify
included and named ([How long the fix took](incident-timeline#fixing)); Done's duration is the
time to repair, in the same words. While the heal runs, the stages move as its card's do. Under it
are links to the incident's record on the device's History, to the device and its Intent where
they help, and, when one was made, **Download the change record (.md)**. Before any decision it
reads "Nothing has run in this incident."

**Mercury's diagnosis**, when one is attached to the incident, is drawn here in full: its
verdict, the runbook, who ran it and how many reads it made, each hypothesis with its strength
and what to do about it, what it ruled out, and where it stopped. It is read-only and uses no
AI. A can't-fix with no diagnosis says so.

## Seen before {#seen-before}

Collapsed. For a lost telemetry stream: whether the same loss was seen on this device before,
when, how it ended and how long that held, with **Open that incident**. It is what the
incident's Needs attention item holds, from the alerts reader's stored reading. It is drawn
only when a past loss matches, or when the search could not be made, which is said: "couldn't
be checked" is never read as "never seen".

## A hand-over's page {#hand-over}

Each hand-over is kept as a version on its own page, `/v2/incident/<its id>/handover/<n>`: its
nine sections, who handed it over and to which teams, a link back to the incident's page and
**Download as Markdown**. It is linked from Fixing it and from The record.

## Evidence {#evidence}

Collapsed, directly under the bottom line: the evidence's one place on the page. Each signal
the problem was classified from (an alert, a log line, a lost stream), with its time; how many
triggers were seen beyond those kept; how many reads of the device the detect pass kept (their
state and time, never configuration text); and each device attached to the incident, with the
reason it was attached. Each change's record is on the device's History, linked from
[What Mercury has done](#what-mercury-has-done).

## The record {#the-record}

Collapsed. The incident's id, its network, its state as its own store keeps it, each
decision's id, its mode, fix kind and tier (the decision's own where nothing has run yet), the
program's hash and its lines (masked), a refused AI plan's hash and its repeating step's
parameter hash (a plan that can be approved says its hashes in What its hash binds), the
times behind the timings, every step with its result, words and time, and who acted, by their
identity as recorded. Every time is in your time zone, its UTC on the hover, as everywhere on
the page. This is the only place on the page an identity is drawn. Each hand-over is listed
last, with **Open the write-up**.

## What an address answers {#addresses}

- **An incident folded into another** redirects to the incident it was folded into, whose page
  says which incident it took in, when and why.
- **An id no record holds** answers "No incident <id> is recorded", and names where it looked:
  the network's open incidents, its newest 200 closed ones, and its step log.
- **An id of another kind** (an alert's or an SDN incident's) answers that its page comes with a
  later slice.
- **A record that could not be read** is said on the page, with **Read again**; whatever could
  be read is still drawn. Not found and not readable are different answers.
- **An incident past the newest 200 closed ones** is drawn from its step log alone, and says
  that its triggers and their times are no longer kept.
