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

**On the page today** the section is labelled **not built yet** and says so: "Not built yet: AI
troubleshooting will be here. Mercury's own account is above, with no AI." An incident Mercury
fixed with no AI call recorded says "Not needed: Mercury fixed it without AI." An AI analysis
kept for the incident (the can't-fix analysis its team's message carried,
[Notifications](notifications#cant-fix)) is drawn under it, labelled advisory: self-healing
never reads it.

**What is built underneath, and not drawn yet.** The parts of AI troubleshooting that need no
AI call exist in Mercury's code (`modules/fixit/`), and no screen shows them yet:

- **The mode**, the installation's: **Manual** by default, in which an AI troubleshoot runs
  only when a verified person asks for one, as a job, and the model is never called for an
  incident on its own; or **Off**, in which none is offered and Mercury's own proposer still
  proposes. There is no automatic mode: a model called with no person asking is a background
  AI feature, turned on only in Settings › AI ([Turn a background AI feature on or
  off](ai-background)), and AI troubleshooting has none.
- **The cap**, $1.00 an incident by default: what the incident's AI calls cost so far, plus
  the next attempt's worst case, against the cap. Over it, the attempt is refused, naming all
  four amounts ("Spent $0.92 in this incident; the next attempt costs at most $0.25, which would
  make $1.17 against the cap of $1.00. Mercury never raises the cap"); exactly at it is allowed.
  A cap that is not a positive amount, or a cost that cannot be read, refuses: there is no "no
  cap".
- **The catalogue and the check.** A proposal, whoever makes it (Mercury's diagnosis, a
  model's answer or a person), names one operation from Mercury's catalogue with its
  parameters, never a command. Today the catalogue holds the telemetry Re-subscribe and its
  Re-add the receiver ([Re-subscribe a lost telemetry stream](telemetry-resubscribe)). Code
  checks it in order, the first refusal ending the check and naming what it compared: the
  catalogue's schema; the incident's own scope (its device, the subscriptions its triggers
  name); the guards that hold any change to a device (a device Mercury manages, no planned work
  holding it); and committed intent, through the operation's own preview. What passes is that
  operation's own preview and hash, for a person to approve. A proposal that repeats a fix that
  already failed in the incident is flagged as a repeat (or a variation, naming each parameter
  that changed), never hidden.
- **Mercury's own proposer**, with no AI: a receiver a run left removed is added back first;
  otherwise, when the lost-stream diagnosis's first hypothesis is complete and its rule is a
  stream stuck at its ends (half-open, no session, or outlived its cause), it proposes
  Re-subscribe for the incident's lost subscriptions. Anything else proposes nothing, and says
  why.
- **The incident's record** of its proposals and of each person's choice (Cancel, Hand over, a
  save), masked at rest. Its attempts are read from the operations' own run records each time,
  never copied, and Cancel runs nothing: the incident stays open with its attempts recorded.
- **What a model would be sent**: the attempts and the catalogue, masked, every person a stable
  label ("person-3f9a1c"), never an address or a name.
- **The hand-over**, a write-up for an engineer in nine sections (summary, impact now, what is
  known, what was tried, what the AI said or that none was asked, the configuration now, next
  steps, notes, cost), built from the records with no AI call, kept as a new version each time,
  and sent to the teams the person chooses among those told about the network's can't-fix,
  with the incident's link.

**Not built yet:** the section's controls (asking for an AI troubleshoot, approving a proposal,
retrying with more information, Cancel and Hand over), the AI call itself, and a screen that
shows or changes the mode and the cap (each holds its default until one does).

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
