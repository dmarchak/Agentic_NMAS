# An incident's page

Each self-healing incident has a page of its own, at `/v2/incident/<its id>`. It tells the
whole story of one incident in one place: when it was detected, what Mercury decided and did,
whether the fix was verified, how long the repair took, and what is left for a person. The
page says one state, the same in its header and in every section, and while a person is
needed it carries that person's one action, under [What to do](#what-to-do). Opening the page
starts nothing and changes nothing: only a person's press does. How each time is found is on
[An incident's timeline and its time to repair](incident-timeline).

**How to open it.** One place per incident, from wherever it is named:

- on [Needs attention](needs-attention), open an item about one incident (a self-healing
  item, or a lost telemetry stream whose device's network holds an open incident for it):
  **Open the incident** is the first link in the opened item;
- on [History](history), or a device's History tab, open a self-healing row: **Open the
  incident** is beside **Open the card**.

The address can be kept and shared; it stays the incident's for as long as its record is kept.

Only self-healing incidents (an id that begins `hi-`) have a page yet. An alert incident and an
SDN incident are on [Needs attention](needs-attention) until theirs are built.

## The header {#header}

The title says what happened in words, and once the incident is resolved how it ended: "and
Mercury put it back", "and it was put back by" the person who approved the fix, or "and it
cleared". Under it:

- **The state**, one of five, said once for the whole page ([One state](#one-state)).
  **Open**: Mercury is watching it or working on it, or a fix a person approved is running or
  has passed its verify. **Needs a person**: it stands on a decision only a person can act on,
  a proposed fix waits, a fix was applied and its verify failed, a fix a person ran stopped
  without fixing it, or its telemetry stream is lost (that fix changes the device's
  configuration, so a person approves it). **Fixed**: a fix was applied and its verify passed.
  **Cleared**: it closed with no fix recorded. **Cancelled**: a person declined the fix
  proposed.
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
- **The four times and TIME TO REPAIR**: Detected, Decided, Fixed and Verified, each from a
  record Mercury wrote at the time, then the time to repair in whole seconds with who it was
  by: "by Mercury's self-healing · policy set by" the name of the person who confirmed the
  network's policy, or "… · approved by" the person who approved the fix. A stage that has not
  happened reads "not yet", and one that was never needed reads "not needed".
- **One line per attempt**: "applied <time> · verified <time>", or "applied <time> · verify
  failed:" with the run's own reason.

**A failed verify never reads Fixed.** When a fix was applied and its verify failed, the state
is Needs a person, the Fixed time is empty with "not fixed: verify failed", the Verified cell
says the verify failed and when, and TIME TO REPAIR reads "not repaired: verify failed".

Every time is drawn in your own time zone; hover over one for its UTC time. People are named
by their display name.

## One state {#one-state}

The page's state comes from one place, and every part of the page says the same: the badge in
the header, What's wrong, What Mercury has done, What to do and AI troubleshooting. It is
worked out from the incident's own records and from what was tried in AI troubleshooting:

| The state | When | What to do says |
|---|---|---|
| Fixed, Cleared, Cancelled | the incident is resolved | Nothing, and why |
| Open | Mercury is still reading the device, or its fix is running | Nothing yet |
| Open | a fix a person approved is running, or passed its verify | Nothing yet, or Nothing now: the incident closes when its symptom clears |
| Needs a person | every other case: a decision only a person can act on, a proposed fix, a failed verify, a fix that stopped without fixing it, a lost telemetry stream | It needs a person, why, and the one action |

So a page never says "No person needed" or "Mercury is working on it" in one place and
"Stopped: nothing more runs unless you choose" in another.

## The timeline {#timeline}

Every recorded event of the incident, oldest first: each trigger, each device attached, each
decision, an approval or a decline, each attempt's apply and verify, and its close. It is open
on a resolved incident and collapsed on one still open.

## What's wrong {#whats-wrong}

What happened, as the decision stated it: the facts in time order, then what Mercury decided
to do about it. On a resolved incident the heading reads "What's wrong (was)".

For a lost telemetry stream it leads with what its Needs attention item says: how long the
device has sent nothing to the collector and what that costs, whether the device answers
Mercury's reachability probe (a reading that cannot say is said as that, in warning colour),
and what Mercury cannot see until the stream is back.

## What Mercury has done {#what-mercury-has-done}

The outcome, then the same five stages the heal's card on
the device's page draws: **Detected**, **Decided**, **Fixing**, **Checking** and **Done**,
each with one sentence, its time and its state. Open a stage for its steps. A failed stage
names its step and why, once. Fixing's time is the whole fix, any wait inside its verify
included and named ([How long the fix took](incident-timeline#fixing)); Done's duration is the
time to repair, in the same words. While the heal runs, the stages move as its card's do. Under it
are links to the incident's record on the device's History and, when one was made,
**Download the change record (.md)**. Before any decision it reads "Nothing has run in this
incident."

**Mercury's diagnosis**, when one is attached to the incident, is drawn here in full: its
verdict, the runbook, who ran it and how many reads it made, each hypothesis with its strength
and what to do about it, what it ruled out, and where it stopped. It is read-only and uses no
AI. A can't-fix with no diagnosis says so.

## What to do {#what-to-do}

The page's state in words, then, while a person is needed, the one action: the same action
the incident's item on [Needs attention](needs-attention) offers, as the page's one primary
button. The page never sends you back to Needs attention to act.

| The incident | The button |
|---|---|
| A fix waits for a person (a proposal) | **Review the fix…** opens the proposal's card under the button, with Approve and Decline ([A self-healing proposal](heal-proposal)) |
| A lost telemetry stream | **Re-subscribe <device>'s telemetry (<subscriptions>)…** opens its card under the button ([Re-subscribe a lost telemetry stream](telemetry-resubscribe)). Run from here, it is recorded as this incident's next attempt, and a repeat of an attempt that failed asks what is different now |
| A fix is proposed under AI troubleshooting | **Go to the proposed fix** moves to the proposal below, where its card is opened |
| A can't-fix, or a fix whose verify failed | **Open <device>**, or **Open <device> (likely cause)** when another device's change is the likeliest cause (a hypothesis, said as one) |
| A dry-run record | its question, **Right** or **Wrong…**: two answers, neither the primary |
| A run holds the device | **Open the run**: the action returns when the run ends |

The button does not move when its card appears: the card is drawn under it. Under the action
are what the item says to do in its own words, **Diagnose…** where the item offers it
([Diagnose a device](diagnose)), how its Needs attention item clears, and links to the device
and its History.

A page that needs nobody (resolved, Mercury working, or a fix under way) draws no primary
button. When the incident still needs a person and its item is no longer on Needs attention
(it cleared there, or a person acknowledged it), the page says so and its button opens the
device. While Needs attention is still being read, the page says that instead: an item not
read yet is never said to be absent.

## AI troubleshooting {#ai-troubleshooting}

The fixes tried in this incident, one line each, with what each cost in AI and **Open the
run**; this incident's AI spend against its cap and today's against the day cap; and what may
be done next. With nothing tried, **Troubleshoot with AI** asks the AI once, as you, its
estimate and the caps drawn before you press. After a fix that did not pass, the section stops:
**Retry with more information…**, **Cancel** and **Hand over…**. Retry asks Mercury's own
diagnosis to plan again, with no AI call, or the AI (**Ask the AI to re-plan**). Either
proposal is drawn with **Open the fix's card…**, the AI's with what it found and what it cites;
a proposal that repeats a failed attempt is flagged; a gap (no Mercury operation does what the
fix needs) and an answer that couldn't be checked are said, with no Approve. Past the
per-incident cap, neither is offered and the section says both figures. Once the incident is
resolved, the section is read-only. Each step is on [AI troubleshooting: Troubleshoot with AI,
Retry, Cancel and Hand over](fixit-troubleshoot).

For a can't-fix, the **AI analysis** kept for the incident is drawn under it in full: its
label and how it has been measured, its rationale, each hypothesis with what it cites and its
recommended next step, and where the answer came from. It is advisory: self-healing never
reads it. An analysis not kept yet, switched off, capped or not answered is said in place.
The one line recording that the analysis ran is under it.

## Seen before {#seen-before}

For a lost telemetry stream: whether the same loss was seen on this device before, when, how
it ended and how long that held, with **Open that incident**. It is what the incident's Needs
attention item holds, from the alerts reader's stored reading. It is drawn only when a past
loss matches, or when the search could not be made, which is said: "couldn't be checked" is
never read as "never seen".

## A hand-over's page {#hand-over}

Each hand-over is kept as a version on its own page, `/v2/incident/<its id>/handover/<n>`: its
nine sections, who handed it over and to which teams, a link back to the incident's page and
**Download as Markdown**. It is linked from the section and from The record.

## Evidence {#evidence}

Collapsed. How many triggers and reads the incident keeps, where its changes are recorded, and
each device attached to it with the reason it was attached.

## The record {#the-record}

Collapsed. The incident's id, its network, its state as its own store keeps it, each
decision's id, its mode, fix kind and tier (the decision's own where nothing has run yet), the
program's hash and its lines (masked), the times behind the header, every
step with its result, words and time, and who acted, by their identity as recorded. Every
time is in your time zone, its UTC on the hover, as everywhere on the page. This is
the only place on the page an identity is drawn. Each hand-over is listed last, with **Open the
write-up**.

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
