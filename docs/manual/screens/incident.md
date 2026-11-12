# An incident's page

Each self-healing incident has a page of its own, at `/v2/incident/<its id>`. It tells the
whole story of one incident in one place: when it was detected, what Mercury decided and did,
whether the fix was verified, how long the repair took, and what is left for a person. It is
read-only: it starts nothing and changes nothing. How each time is found is on
[An incident's timeline and its time to repair](incident-timeline).

**How to open it.** One place per incident, from wherever it is named:

- on [Needs attention](needs-attention), open a self-healing item about one incident: **Open
  the incident** is under Why this happened;
- on [History](history), or a device's History tab, open a self-healing row: **Open the
  incident** is beside **Open the card**.

The address can be kept and shared; it stays the incident's for as long as its record is kept.

Only self-healing incidents (an id that begins `hi-`) have a page yet. An alert incident and an
SDN incident are on [Needs attention](needs-attention) until theirs are built.

## The header {#header}

The title says what happened in words, and once the incident is resolved how it ended: "and
Mercury put it back", "and it was put back by" the person who approved the fix, or "and it
cleared". Under it:

- **The state**, one of five. **Open**: Mercury is watching it or working on it. **Needs a
  person**: it stands on a decision only a person can act on, a proposed fix waits, or a fix was
  applied and its verify failed. **Fixed**: a fix was applied and its verify passed. **Cleared**:
  it closed with no fix recorded. **Cancelled**: a person declined the fix proposed.
- **The level** its Needs attention item has or had (Critical or Warning), or **No person
  needed** for an incident that never needed one.
- **The device**, a link to its page, with the network and how many devices were attached to
  the incident.
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

## The timeline {#timeline}

Every recorded event of the incident, oldest first: each trigger, each device attached, each
decision, an approval or a decline, each attempt's apply and verify, and its close. It is open
on a resolved incident and collapsed on one still open.

## What's wrong {#whats-wrong}

What happened, as the decision stated it: the facts in time order, then what Mercury decided
to do about it. On a resolved incident the heading reads "What's wrong (was)".

## What Mercury has done {#what-mercury-has-done}

The outcome, then the same five stages the heal's card on
the device's page draws: **Detected**, **Decided**, **Fixing**, **Checking** and **Done**,
each with one sentence, its time and its state. Open a stage for its steps. A failed stage
names its step and why, once. While the heal runs, the stages move as its card's do. Under it
are links to the incident's record on the device's History and, when one was made,
**Download the change record (.md)**. Before any decision it reads "Nothing has run in this
incident."

## What to do {#what-to-do}

What is left for a person, in words, with links to where it is done: Needs attention, the
device's page, its History or its Intent. This page has no buttons: an incident's actions are
on its Needs attention item.

## AI troubleshooting {#ai-troubleshooting}

AI troubleshooting is not built yet, and the section says so. An AI analysis kept for the
incident today is drawn under it, labelled advisory: self-healing never reads it.

## Evidence {#evidence}

Collapsed. How many triggers and reads the incident keeps, where its changes are recorded, and
each device attached to it with the reason it was attached.

## The record {#the-record}

Collapsed. The incident's id, its network, its state as its own store keeps it, each
decision's id, the program's hash and its lines (masked), the times behind the header in UTC,
every step with its result and words, and who acted, by their identity as recorded. This is
the only place on the page an identity is drawn.

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
