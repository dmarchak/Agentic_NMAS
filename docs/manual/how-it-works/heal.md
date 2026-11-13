# Self-healing: a device restored to its intent

Self-healing finds a device that has departed from its committed intent and, by the network's
own policy, either records what it would do (**Dry run**), restores it without a person (a
Tier 1 fix in **Auto**), proposes the fix to a person (Tier 2), or says it cannot fix it. It
restores intent: it never adds anything intent does not hold. Each network's policy is its own,
on its **Self-healing** tab ([Self-healing](settings#self-healing)), and **Turn off** stops a
network's healing at once.

![Self-healing, one incident: a trigger (a log line, an alert, an adjacency, a drift record) opens an incident on a device; the detect pass reads the device, the same read as Check drift now, until the grace period settles it; the decision finds the approved state, the golden that matched intent, checks the guards in order and compares the device with it, classing each unit and its tier: in dry run it records what it would have done for a person to mark right or wrong; in Auto a Tier 1 fix is applied as the policy, holding the device, through the deploy's nine stages, verified and rolled back on failure; a Tier 2 fix waits for a person; anything else is can't fix. Every step is recorded in the step log and History, a healed device's golden committed and read again, and the network's team is told.](diagrams/heal.svg)

## Detect {#detect}

A trigger opens an **incident** on one device: a configuration change in its log that no
Mercury operation made, an alert, an adjacency that went down, or a drift record. Triggers about
the same cause fold into one incident. Self-healing's runner passes over every network with an
incident every 30 seconds, and at once when a trigger arrives. One pass, per network:

1. `mode`: it reads the network's mode. Off, or stopped everywhere, closes every incident
   watching or standing, and nothing new starts.
2. `lock`: it holds the network, one pass at a time across Mercury's processes.
3. `judge`: it judges each incident's grace period.
4. `read`: when a read is due, it reads the device, the same read and comparison as **Check
   drift now** ([Check drift](drift-check)): the first at once, the second a grace period later
   (2 minutes on a network marked lab, 15 otherwise). A device that changes again restarts its
   grace period, so a person's change in progress is never healed half-way.
5. `members`: a device attached to the incident (its far end, say) is read once, and never
   healed on its own.
6. `settle`: an incident the two reads agree on is handed to the decision. One that was
   standing on a decision and changed again, but whose two reads find the same departure that
   decision judged, stands on that decision again instead: there is no second decision of the
   same thing ([Standing](#standing)).
7. `proposals`: each proposal still waiting for a person has its device read again, and is
   withdrawn when it no longer fits ([Withdrawn](heal-proposal#withdrawn)).
8. `standing`: each can't-fix standing at its golden on a symptom has that symptom read again
   from the readers' stored values (no device is read). Every symptom gone, and nothing logged
   about it for the flap window (10 minutes by default) since it was last seen, ends it:
   "cleared by itself at HH:MM UTC, nothing to do", and its item leaves Needs attention. A time
   Mercury measured is said "at HH:MM"; "by HH:MM" is only ever an estimate or a deadline.

The detect pass changes nothing on any device.

## Decide {#decide}

The decision takes one settled incident and answers heal, would heal, propose, can't fix or
held. Its steps:

1. `claim`: it takes the ready incident, once.
2. `stops`: the kill switch, the network's mode (and a halt in force) and planned work.
3. `approved`: it finds the approved state, the device's last golden that matched its intent. A
   golden that departs from intent leaves no approved state, and the device is held.
4. `guards`: the guards in their order: a recent change nearby, many devices departing at once,
   a person working on the device, the grace period, and the rates per device and per network.
   The first that applies is named in the decision with both values it compared.
5. `read`: the device is compared with the approved state.
6. `classify`: each unit that departs is classed by kind, each kind has its tier, and the
   program (the exact lines it would send) and its hash are computed.
7. `decide`: in **Dry run**, what it would have done is recorded and nothing is sent; in
   **Auto**, a Tier 1 kind the policy allows is healed; a Tier 2 kind is proposed to a person;
   a Tier 3 or 4 kind is can't fix.
8. `record`: the decision is recorded in the network's heal decisions and its step log.

**One unit is one feature, with what only it uses.** A unit is one feature on one section (an
interface's OSPF authentication is one unit, however many lines). A definition that only one
added line uses by name is one unit with it: an ACL and the `ip access-group` applying it, a
class-map, its policy-map and the `service-policy`, a key chain and its use, a prefix-list and
its `neighbor … prefix-list`, an object-group and its ACL, a track and its static route, an IP
SLA and its track. So an ACL added and applied outside intent is one fix, removed or kept
together. A definition an unchanged line also uses stays its own unit.

**A security control is a person's** ([Remove it or keep it](heal-proposal#keep)). Removing or
changing a line outside intent that adds a security control (routing authentication and key
chains, an ACL or its application, AAA, crypto and SSH, SNMP restrictions, control-plane
policing, port security and 802.1X, `transport input`; declared per platform by line shape) is
Tier 2: proposed, never automatic, because it may be half of a rollout whose far end is not
configured yet. Adding back a missing control stays Tier 1. Accounts, AAA's login lines, crypto
keys and Mercury's own path stay Tier 4. A network may answer yes to "may Mercury revert a
one-sided security change that broke an adjacency?" (`heal_security_revert_adjacency`, no by
default): then such a change on an interface or routing process, on a device whose incident
holds an adjacency down and no other device, is Tier 1 (`security_revert`), healed in Auto only
where the policy names that kind.
**What the decision says.** Its words are plain. First come the facts Mercury holds, each at its
time: the change (who made it, as the configuration line named them, and what it changed) and
each symptom. Then comes what Mercury did or would do, with the tier as a label after it. The
fix kind, the guard and the mode are the record's own fields, under **Details for the record**.
Where Mercury holds both ends of a cause, it adds a **likely cause** after the facts, labelled
as a hypothesis. Both ends means one of two things:

- a change on an interface, and a symptom on that interface after it. An ACL the same change
  added and applied there, whose entries permit no OSPF, is said as a fact, and the hypothesis
  is that the ACL drops OSPF there;
- a router-id the change set, and a duplicate router-id report naming it.

A symptom on another interface, or before the change, links nothing: Mercury never guesses.

**A can't-fix whose likeliest cause is another device's change.** A symptom on a device whose
configuration matches its intent may come from another device. When another device's change,
made outside Mercury and not fixed yet, came at most 10 minutes before the symptom, the
can't-fix leads with **Open <device> (likely cause)**, labelled as a hypothesis. The device is
the one the symptom's own records name, or the only such device in the network. Mercury names
none when several unnamed devices changed. **Acknowledge…** records the cause, if you know it.

The rates per device and per network are not counted for an incident whose read found the
device at its golden: it has nothing to heal, so a person's revert ends "nothing to heal", never
a hold for the rate the change's own would-heal used. A symptom read gone when it is decided,
but seen less than the flap window ago, is checked again once that window has passed, never
called a can't-fix: a link still flapping reads up between its drops, so it is checked again
once, and a link still flapping then is a can't-fix as before.

## Standing on its decision {#standing}

A decision that leaves the problem in place (in dry run, "would heal"; a can't-fix; a hold that
a person resolves) keeps its incident open, **standing** on that decision, so one change stays
one incident however long it takes a person to deal with it:

- **A symptom that arrives later on another device folds into it** by the usual rules: the
  device is inside the changed device's blast radius, or at the far end of the link the symptom
  names. A router whose path to the collector runs through the changed router, losing its
  telemetry a minute later, is attached to the changed router's incident, not a can't-fix of
  its own, and the team is told once. This holds for about four minutes after the decision
  (250 seconds); a symptom on another device later than that is judged on its own, so a
  decision that has stood for days never hides an unrelated fault. An alert rule whose pending
  period plus its group's evaluation interval is longer than that can fire too late to fold:
  while self-healing is on, Needs attention names each such rule with both numbers, and says
  so too when the alert reader's last read does not hold them.
- **The drift check finding the same departure joins it:** no second incident, and no second
  decision of the same thing.
- **Anything else that changes the device** (a configuration change from outside Mercury, a
  person's revert, the drift check finding a different departure) sends it back to be judged
  again after the grace period. A revert that puts the device back at its golden ends "nothing
  to heal". A symptom the reverted change caused is that change's, so it is not judged again as
  a can't-fix of its own.
- **It ends** when the device is read back at its golden or its intent: a later decision of
  nothing to heal; a drift check that read the device at its golden after the decision (the
  check names each device it read clean, and only a read counts, never a device missing from
  the list); or, for a can't-fix at its golden on a symptom, the symptom read gone and quiet for
  the flap window, by the detect pass or by Mercury's own diagnosis before its notice ("cleared
  by itself at HH:MM UTC, nothing to do"). A hold because the device's golden departs from its
  intent is not ended by a read at that golden. Turning self-healing off ends every standing
  incident.

Each end is a decision of nothing to heal, recorded on the incident with what read the device
and when, so History shows one row per incident, its newest outcome on it, and the incident's
Needs attention item leaves. A can't-fix is told to the team once per incident, however often a
standing incident is judged again.

## Act and verify {#act}

A heal runs as its own job, as the policy, on behalf of the person who confirmed it, and every
step is the deploy pipeline's ([Deploy](deploy)):

1. `take`: it takes the decision, once.
2. `stops`: the kill switch, the mode, the network's stage, the policy and planned work, again.
3. `read`: it reads the device again.
4. `plan`: it recomputes the program from that read and refuses unless its hash is the
   decision's. Nothing is sent when the device moved.
5. `authorise`: each removal carries the policy's reason; a dangerous line is refused.
6. `apply`: holding the device, it applies the program through the deploy's nine stages.
7. `intent`: each healed unit is checked to be at intent.
8. `symptom`: the symptom that opened the incident is read again, every 30 s until it is gone
   or its bound ends. Each read is kept under this step in the heal's record: when, the
   reader's store that was asked, and gone, still there or not read since the change.
   **A heal that puts the heartbeat applet back waits for its heartbeat.** When a fix re-applies
   the applet that intent's syslog block declares as the device's heartbeat, the heartbeat itself
   is a symptom: the heal waits for the device's next heartbeat line, read from the arrivals
   Coverage already stores for the whole fleet (no device is read). It waits up to about 2.5
   times the sum of the applet's own interval in intent and the 2 minutes the logs read takes
   to hold a line: 2.5 × (300 + 120) = 1050 s for a 300 s heartbeat. The heal is healed and verified only when the heartbeat
   arrives; if none has arrived by then it ends **symptom remains** (amber), saying how long it
   waited and the newest heartbeat it read. Any other applet, and any other missing line, keeps
   its own symptom.
9. `saved`: once verified, the running configuration is saved and the device released.
10. `golden`: the device is captured and read again against its new golden.
11. `record`: the outcome is recorded and the incident closed.

A failed verify rolls back what landed, and **halts** the network's healing until a person
lifts it ([Lift the halt](heal-proposal#halt)). A configuration healed whose symptom remains is
amber, "symptom remains", never green.

**Who a heal is by.** A heal is Mercury's own: the chip, the held-device banner and the card say
**by Mercury's self-healing · policy set by <name>** (an approved proposal's, **approved by
<name>**), the person by their display name, never their address, and never "you", even when
the person looking set the policy.

**While a heal runs**, the top bar's **In progress** chip lists it as one row,
**Self-healing**, on its device, and the row's words are the step the run is in ("Apply · step
6 of 11"), never "starting". The device's page opens the run's card in place of its tab, and
the card draws the run as ONE run on one stepper of five stages, from what was seen to its end:

| Stage | Its steps | What it says |
|---|---|---|
| **Detected** | the incident opening on its first trigger, and the grace period waited out | what was seen ("edge1's configuration changed outside Mercury") |
| **Decided** | the decision's eight steps, done by the detection job, each with its time | the decision ("Heal: remove …") |
| **Fixing** | the act's steps up to and including Apply; the deploy's stages inside Apply | "Applying 3 lines to edge1…", then "Applied 3 lines to edge1" |
| **Checking** | Check intent, Read symptom, Save startup, Check golden | "Waiting for edge1's symptom to clear · up to 750 s: 120 s left", then "edge1 at intent; its symptom gone"; a heal that put the heartbeat applet back, "Waiting for edge1's heartbeat · up to 1050 s: 120 s left", then "edge1 at intent; its heartbeat back" |
| **Done** | Record | the outcome and how long from when it was seen ("Healed and verified in 4 min 12 s") |

Each stage is one plain sentence, its time (in your zone; UTC on hover) and its state (**done**,
**in progress**, **not started**, **failed**, **not fully done** or **not reached**); nothing is
drawn done that the run has not recorded. The five sit in one row on a desk; where the card is
too narrow for the row they run down, one under the other. Open a stage to read its steps, one
line each in two to four words ("Read <device>", "Recompute program", "Apply", "Check intent"),
the full words on hover, with each step's time and one-line outcome; while it applies, the
deploy's own stages are listed inside **Apply**, never as a second stepper. A step that waits
says how long: the symptom's read waits "up to 150 s" for an adjacency (up to 750 s for an
alert, up to 1050 s for a 300 s heartbeat), and its stage counts it down from the time the step began and the length the run
declared; when the time is up it says so and waits for the run's next step. The card moves by
itself at each step, over the live connection; nothing asks on a timer. The card starts when
the heal's job does: the grace period is drawn done under Detected once it has passed, and is
not drawn live while it runs.

**Where a run's outcome is read.** When it ends, the chip keeps it under **Finished, not opened
yet** for every person until each has opened it (nobody started it, so it is everybody's to
read), and the device's page opens its card: the outcome first (green only for healed; amber
for a heal partly shown or whose symptom remains; red for nothing sent, a rollback or a
failure), who it was by and when it started and ended, then its five stages, each said in at
most 12 words (the Decided stage names the fix in plain words, "Heal: remove the static
route"; the lines it sends are in its steps, one level down). A failure is named at its stage,
with why, in one line ("Apply failed: …"), the whole of why on its step's line when the stage
is opened; a later stage that failed too says only that it failed ("Check intent failed"), so
the failure is said once. Done is never green over a partial or a failure. What a step that did not pass read sits under that step alone, closed, as **What it
read** (its checks, one line saying its reads, and every read one level further down); a step
that passed shows no checks. The card is kept for 30 minutes in the running app's memory; after
that, or after Mercury restarts, the run's row on the device's History (or on History, kind
Self-healing) has **Open the card**, which opens the same card on the device's page, drawn
from the step log: the same five stages, its outcome and who it was by.

A **can't-fix** is a decision, not a run: nothing ran, so nothing is listed as finished. Its
outcome is its Needs attention row, which stays until a person acknowledges it or a later heal
ends healed; opened, the row says why it stopped and carries one closed line under it, **The
steps Mercury took: stopped at <step> · N steps · Show**, which opens the same stages (the
decision's steps, the one it stopped at named); the team's notice carries each step and its
result ([Notifications](notifications)). The decision worked: it decided that a person is
needed, so its Decided stage reads **Can't fix: needs a person**, in amber, and its Decide step
"needs a person", never "failed" in red.

## The records {#records}

Every incident is one row on **History**, kind Self-healing, its line the newest outcome with
the mode on it ("dry run" is never read as Auto). A decision's own outcome (would have put it
back, a proposal, can't fix) leads with what happened in plain words, the incident's own title
("edge-b: static route added outside Mercury"), never the configuration line, which its detail
quotes; its Needs attention item leads with the same words. Opened, the row says what
happened (each fact at its time, then a likely cause labelled as a hypothesis where Mercury
holds both ends of one) and what Mercury did or would do. **Details for the record**, closed
until you open it, holds every step and its result (a step that read says its reads after its
words, counted: how many, of what, how they went and the last one; in a finished record no step reads
running: a step recorded as begun with no end of its own reads done, ended when the next step
began, or names the later step that holds its outcome), the incident and decision
ids, the program
(masked) and its hash, the policy, and the records the incident wrote: the deploy receipt, the
golden commit (`Source: heal_to_intent`, `Actor-Verified: policy`), the golden read again, the
change record and the NetBox journal entry. A healed incident is History and a notice, never a Needs attention
item.

**Each incident has its own page**, `/v2/incident/<id>` ([An incident's page](incident)): its
four recorded times and its time to repair, its five stages, what is left for a person, and its
record. A self-healing row on History, and a Needs attention item about one incident, open it with
**Open the incident**, and the team's message links it.

**Download the change record (.md)**, beside **Show the change** on the opened row, saves the
incident's change record as a Markdown file named for the device and the incident, masked as
Mercury keeps it, for a heal and an action alike. It is a read of the step log: it sends
nothing and asks no model. A dry run has no change record, since nothing was sent, and neither
has a heal refused before its program was computed, so their rows draw no link. The network's team is told as its Self-healing tab chooses ([Notifications](notifications)).

An **action** (a bounce, a clear, a dampening change) is named as one on its row: its line names
the port or the neighbour and how it ended ("edge1 GigabitEthernet4 bounced, still flapping",
"edge1's BGP neighbour 192.0.2.3 cleared, session not back", "would bounce" in dry run, never "would
heal"). Opened, it shows what it acted on, its **planned window** and the **far end** the window
named, whether anything was sent, verify's result (the confirm, the adjacency, the stability
window), its **rollback** (the repair, the device's own revert, or why none applies: a clear is
never put back), and its own records: the dampening change it raised, the privileged command's
run of a clear, the intent commit of a dampening change and its put-back, and the verify read.
The row is on the far end's History too, so the device across the link shows the bounce that
took its port down. Each act keeps a **change record** written by Mercury's code with no AI call,
in the same sections as a heal's: what was acted on and why, the program, the risk by its stated
rule, the verify, the rollback and what the act did of it, the window with its far end, who
allowed it (the policy, or the person who approved it), and its status. Its row downloads it as
a heal's does.

## Dry run: Right or Wrong {#mark}

In dry run nothing is sent; each would-heal is a record for a person to judge. It is an item on
**Needs attention** for up to 7 days, carried by the device's drift item when there is one. Its
line says what changed and what Mercury would have done, for example "edge1: “logging host
192.0.2.10” was removed from the global configuration. Mercury would have put it back itself,
but Default is watching only (dry run), so nothing was sent". **Was that right?** opens it.
Opened, it says what happened, each fact at its time in your time zone, and then **Was this the
right fix?** in place. The same question is under the record on the device's **History** (or
History, kind Self-healing):

- **Right** records that what it would have done was right, with your name.
- **Wrong…** opens a reason: type why it was wrong (what it would have broken, or the fix that
  was right) and press **Mark it wrong**. Pressing Enter in the reason sends nothing.

Each is a verified person's, sends nothing to a device, and is answered in place. A mark is
drawn on its control wherever the record is drawn again: the answer chosen shown selected, with
"Marked right by <person> at <time>" beside it. Pressing the other answer changes it. Every mark
is recorded in the network's heal decisions, the newest counting, and every mark stays. The marks are counted per fix kind as the dry run's false-positive rate, which a network's
Self-healing tab shows against production's bar, and the record's Needs attention item leaves.
A mark is refused, naming what it compared, for a record that is not a dry run's, or for a
caller who is not a verified person. When the heal decisions cannot be read, the record says so,
which is not the same as unmarked.

## Held {#held}

A device is **held** from healing when a guard says a person must resolve something first. It
is an item on **Needs attention**, "Self-healing holds <device> on <network>: <the guard>",
naming the guard and both values it compared, with what to do:

- **its golden departs from its intent**: there is no approved state to heal to. Adopt the
  change into the device's intent, or capture the device after reverting it;
- **healed past its rate** (more heals of the device in an hour than the policy allows): read
  why it keeps departing on its History, and fix what changes it;
- **many devices at once** (more devices departed within one grace period than the policy
  allows): one item for the network, naming the devices; find the rollout, template or event
  that moved them. A fleet-wide departure is escalated, never healed.

The item leaves when the device's next decision replaces it, or when you acknowledge it with
what you resolved. A hold self-healing checks again by itself (planned work, a recent change, a
person working, the grace period) is no item: it is on the device's History.

## Halted and interrupted {#halted}

A network **halts** after the same fix twice, too many heals in an hour, or a heal that was
rolled back or failed after sending: one Critical item, with **Lift the halt…**
([Lift the halt](heal-proposal#halt)). A heal whose job ended before it recorded its outcome is
**interrupted**. When it had started its apply, what reached the device is not known, so it
halts the network too; one that ended before its apply sent nothing and halts nothing. Its item
says to read the heal's steps and the device against its golden and acknowledge with what you
found, and, when the network halted, to lift the halt on its own item.

## Actions, and the flap record {#actions}

Some faults are not configuration: a port down while it is administratively up with its far end
up, a BGP session that is not Established with no configuration cause, an OSPF adjacency stuck
on an interface with one neighbour, or a port still flapping. For these self-healing will have
**actions**: a port bounce, a clear of one named BGP neighbour, an OSPF adjacency reset (the
bounce on that interface) and a dampening change proposed for a person. An action changes no
configuration line, or proposes a change to intent, and is named as an action wherever it is
drawn. An action is chosen only from the diagnosis's first hypothesis, when its evidence is
complete and it is that action's rule; a decisive finding above it, such as an MTU mismatch,
means no action. Before anything is sent it must pass its guards in order: the state read again
just before the send (a port that came back by itself is left alone), the far end read up and
not held or being worked on, never the interface Mercury reaches the device on, once (a second
bounce of a port within the repeat window becomes the dampening proposal), and a flap measured
from the logs.

The **port bounce** and the **OSPF adjacency reset** through it are built ([The port
bounce](#bounce)), and so are the **clear of one BGP neighbour** ([The BGP session
clear](#clear)) and the **dampening proposal** ([The dampening proposal](#dampening)). A
device's intent can hold dampening on an interface (`dampening: true` under the interface in its
host_vars, the bare `dampening` line, the platform's defaults), committed and deployed through
the intent editor like any other change, and Mode B removes it again: `no dampening` was
measured to remove exactly that line on IOS and IOS-XE. Under all of them runs
the **flap record**: each time the network's syslog is read, every `%LINK-3-UPDOWN` and
`%LINEPROTO-5-UPDOWN` line is recorded as a transition of its interface at the time Mercury
received it, never by the device's clock, for networks whose self-healing is on. A link and its
line protocol going down together count once. A flap is **A flap: transitions of one interface
within** on the Self-healing tab (3 in 10 minutes by default); the record keeps an hour. A
transition received inside a planned window that takes the interface down on purpose (a
bounce's own window, a bounce of the link's other end, or a planned restart of the device) is
the operation's, not a flap, and the count says how many it left out.

A problem self-healing held back (a recent change, a person working) is judged on what its
sources read **when it is decided**, not on what was seen when it was raised: a link or
adjacency back up by then, and quiet for the flap window since it was last seen down, is
nothing to heal, and raises no "could not fix" item. One back up but seen down less than the
flap window ago is checked again when the window has passed, and raises no item meanwhile; one
still flapping then is judged as before. A can't-fix whose diagnosis, run before its notice,
reads the link or the device's reach back, and which stays quiet for the flap window, ends as
cleared by itself, and no "could not fix" message is sent ([Notifications](notifications)).

## The port bounce {#bounce}

A **port bounce** shuts a port and brings it straight back up, in one write, inside the device's
own revert timer. It changes no configuration line, it is never saved, and it is named as an
action wherever it is drawn. The **OSPF adjacency reset** is the same bounce on an interface
that holds exactly one OSPF neighbour stuck short of FULL, so it resets that one adjacency and
nothing else on the router. Neither is on by default: a network's Self-healing tab lists each as
a Tier 1 kind, **Dry run only** until a person allows it in Auto. In **Dry run** the bounce is
recorded as "would have bounced <device> <port> (program <hash>)" for a person to mark right or
wrong, and nothing is sent.

**How it is decided.** When self-healing cannot fix a port down while it is administratively up
(an Alert), Mercury diagnoses it first. Only when the diagnosis's first hypothesis is the port
down with its far end up, or the interface's one OSPF neighbour stuck, is a bounce considered:

1. `choose`: the action is chosen from the diagnosis's first, complete hypothesis, never from AI
   text; a decisive finding above it, such as an MTU mismatch, means no action.
2. `stops`: the kill switch, the mode, a halt and planned work, as for any heal.
3. `rates`: the heals per device and per network an hour.
4. `fresh`: both ends are read again, with the device's own route back to Mercury. These reads
   are the decision's own: each is listed under this step in the step log, naming its masked
   answer, and none is a Show commands row on History
   ([How Show commands works](show-commands#an-operations-reads)).
5. `guards`: the port still down (one that came back by itself is left alone); the far end up,
   not held and not being worked on; never the interface Mercury reaches the device on, never
   one the device's own `show ip cef` (or `show ipv6 cef` for an IPv6 manager) names as its way
   back to Mercury, and never the device's only path; once an hour per port, a second need
   within the repeat window being a dampening change for a person; the flap record readable;
   the configuration archive in the device's intent, which its revert timer needs (its path,
   `archive.path` in the device's host_vars, or an `archive` block intent keeps as an
   unmodelled line, as intent committed before the field holds it; the editor refuses a
   document holding both, since both would be sent); and the
   revert timer measured on the device's platform (IOS and IOS-XE, by the operator's trial).
6. `decide`: in Auto, with the kind allowed, it bounces; otherwise it records what it would have
   done.
7. `record`: the decision is recorded in the network's heal decisions and its step log.

**How it runs.** The bounce is its own job, as the policy, holding the device for every session:

1. `take`: the decision, once.
2. `stops`: the kill switch, Auto, the network marked lab, the policy and planned work, again.
3. `hash`: the program is computed again and refused unless its hash is the decision's. The
   program is `configure terminal revert timer 2`, `interface <port>`, `shutdown`, `no
   shutdown`, `end`; its `shutdown` carries the policy's reason, in the hash and the record.
4. `hold`: the device is held, so no other operation runs on it.
5. `pre-read`: the running configuration (before), the port, a pending revert, the interface
   holding the management address and the route to Mercury, all read again on the bounce's own
   session; any one that refuses sends nothing.
6. `window`: a planned window is recorded on the device, naming the port, before anything is
   sent: 6 minutes 38 seconds (the 2-minute timer, the 3-minute watch past it and the 98-second
   settle bound). It covers the link's **far end** too: the device and interface committed
   intent puts on the same IPv4 or IPv6 network. Adjacency drops inside it are explained at both
   ends, never an item, and neither end's UPDOWN lines are a flap. A window that cannot be
   recorded, or whose far end cannot be told because committed intent cannot be read, sends
   nothing.
7. `send`: the one batch. A cut session cannot leave the port shut: the device receives the
   batch whole, and its timer reverts it if Mercury never comes back.
8. `watch`: a new session every 10 seconds.
9. `confirm`: `configure confirm` is sent only once Mercury is back in and the port is up/up
   with the running configuration equal to before, line for line, within 98 seconds (2.5 times
   the slowest settle the trial measured, 39 s). Otherwise nothing more is sent, and the device
   reverts itself when its timer ends.
10. `verify`: an OSPF reset's adjacency must reach FULL; the configuration is read again and
    must not have moved.
11. `stable`: once the device is released, the stability window (the flap window's minutes)
    must hold no transition to down after the bounce's own up.
12. `repair`: when the end is not as before, `no shutdown` (and `configure confirm` only when a
    revert is still pending), read back, each step saying what it achieved.
13. `record`: the outcome on the device's **History**, kind Self-healing.

**What it ends with.** "Bounced; configuration unchanged" is on History, never a Needs
attention item, and the team is told under **every automatic heal** ([An action's end,
told](notifications#actions)). Every other end is one item, "Self-healing's bounce of <device>
<port>", told to the team in the item's own words,
until a later bounce of that port ends bounced, 7 days pass, or you acknowledge it with what you
found: bounced once and **still flapping** (the [dampening proposal](#dampening) is the next
need, for a person, and the item says whether it waits);
the OSPF adjacency **not formed**; **not verified** (the stability window could not be read);
**reverted by its timer** (no confirm, the device back as before); **repaired**; **NOT
RESTORED** (a reload returns it, since nothing was saved); or **nothing was sent** (a guard
refused it at its apply). Reverted, repaired and not restored also **halt** the network's
healing until a person lifts it. A bounce **held** by a guard (the far end held or being worked
on) is an item too: it is not tried again by itself.

## The BGP session clear {#clear}

A **session clear** resets one BGP neighbour's session, the one intent holds, named by its
address: never every neighbour at once (`clear ip bgp *` is never sent), and never an address
typed by anyone. It changes no configuration line and is named as an action wherever it is
drawn. It comes in two forms:

- a **hard clear** (`clear ip bgp <neighbour>`, or `clear bgp ipv6 unicast <neighbour>` for an
  IPv6 neighbour), only of a session that was **not Established in two reads in a row**: it had
  no routes to lose;
- a **soft clear** (the same with `soft`, a route refresh), only of an **Established** session;
  it resets nothing. Nothing chooses it yet: it is for a session receiving fewer routes than
  intent expects, and intent does not yet say how many routes a neighbour should send.

**No clear at all** for a neighbour in **Idle (Admin)**, one shut by configuration, or one whose
last reset names a wrong remote AS: a clear cannot fix those, so the incident stays an Alert with
its diagnosis. A clear must also be **measured on the device's platform** first: what it asks,
what answers it, and how long the session takes to come back, by a probe on a real device. The
clears are measured on IOS-XE, in both address families: neither asks a question; the soft clear
resets nothing, and the hard clear's session is back in about 3.5 s (IPv4) and 5 s (IPv6), so
verify waits about 2.5 times that. On IOS none is measured yet, so a clear there is refused,
naming the measurement it waits for.

**Where it runs, and who decides.** On a network marked lab it is Tier 1: the Self-healing tab's
**BGP session clear** under Tier 1 allows it in Auto, and in **Dry run** it is recorded as "would
have cleared <device>'s BGP neighbour <address>" for a person to mark right or wrong, with
nothing sent. On any other network it is Tier 2: with **BGP session clear** under Tier 2 set to
Propose, it waits on Needs attention for a person's **Approve…** with a reason, and runs as that
person. Neither is on by default.

**How it is decided.** When self-healing cannot fix a BGP session down (an Alert), Mercury
diagnoses it first. Only when the diagnosis's first hypothesis is the session not Established
with no configuration cause is a clear considered:

1. `choose`: the clear is chosen from the diagnosis's first, complete hypothesis, never from AI
   text.
2. `stops`: the kill switch, the mode, a halt and planned work, as for any heal.
3. `rates`: the heals per device and per network an hour.
4. `fresh`: the neighbour is read again (the second of the two reads), with the device's own
   route back to Mercury. These reads are the decision's own, listed under this step in the
   step log, never Show commands rows on History.
5. `guards`: the session still not Established (one that came back by itself is left alone);
   never a clear that would withdraw the route the device reaches Mercury by (a hard clear of
   the neighbour that route is learned from is never sent); once per neighbour per incident;
   then the clear's own plan: the neighbour is intent's, the two reads, no shut neighbour or
   wrong remote AS, and the clear measured on the device's platform.
6. `decide`: on a lab network in Auto, with the kind allowed, it clears; elsewhere it is
   proposed; otherwise it records what it would have done.
7. `record`: the decision is recorded in the network's heal decisions and its step log.

**How it runs**, as the policy on a lab network or as the person who approved it elsewhere:

1. `take`: the decision, once.
2. `stops`: the kill switch, the mode, the network marked lab (for the policy), the policy and
   planned work, again.
3. `plan`: the clear is planned again and refused unless its hash is the decision's.
4. `hold`: the device is held, so no other operation runs on it.
5. `route`: the device's route back to Mercury is read again on the clear's own session.
6. `window`: a planned window is recorded on the device, naming the neighbour's interface,
   before anything is sent: the clear's verify bound and a minute. A hard clear's window names
   the neighbour's device too, when committed intent holds the neighbour's address. The session
   drop it causes is explained at both ends, never an item. A window that cannot be recorded
   sends nothing.
7. `send`: the neighbour is read again and kept (its last reset reason is evidence a clear
   destroys); a hard clear is never sent to a session Established by then. The command is sent
   once, and only the question its measurement recorded is answered.
8. `verify`: the session is read until it is Established, within about 2.5 times the time its
   measurement took (a soft clear: still Established, no connection dropped, the refresh sent).
9. `record`: the run on the device's **History** (a privileged command, with its reason and the
   session as it was before) and the outcome, kind Self-healing.

**What it ends with.** Cleared; cleared and the session **not back** within its bound; a soft
clear that **reset** the session (which halts the network's healing until a person lifts it);
**not verified** (the read after could not be understood); **refused by the device** (nothing
was cleared); or **nothing was sent**. Rollback does not apply, and the record says why: a
session that was not Established had nothing to lose, and a route refresh resets nothing.

Cleared is on History, never a Needs attention item, and an automatic clear is told under
**every automatic heal**. Every other end, and a clear **held** by a guard, is one item,
"Self-healing's clear of <device>'s BGP neighbour <address>", Critical when the session did not
come back or a soft clear reset it. Its action is to read the clear's steps on the device's
History, check the session and the neighbour's own device, then acknowledge with what you found;
the team is told in the same words ([An action's end, told](notifications#actions)). It leaves
when a later clear of that neighbour ends cleared, 7 days pass, or you acknowledge it. A clear
waiting for a person off a lab network is the proposal's own item, opened with **Review the
fix…**.

## The dampening proposal {#dampening}

A port that keeps flapping after its one bounce is not something a second bounce fixes. The
industry's answer is to suppress it: IP event dampening holds a flapping interface down until
it has been quiet for a while, so the routing protocols over it stop churning. That is a change
to the device's intent, so it is never automatic: self-healing **proposes** it, and a person
approves or declines it.

**When it is proposed.** Only in **Auto**, after a real bounce: when the bounce's stability
window reads the port going down again after it came up (bounced once, **still flapping**), or
when the port needs a second bounce within the repeat window (24 hours by default). In **Dry
run** nothing was bounced, so nothing is proposed, and the record says so. It is proposed only
when **Dampening** under Tier 2 on the Self-healing tab is set to Propose (it is not by default);
otherwise the record says the policy does not propose it. One proposal waits per port.

**What it proposes.** The device's intent gains `dampening: true` on that interface (the bare
`dampening` line, the platform's defaults), and the deploy that intent renders: `interface
<port>`, ` dampening`, `exit`, nothing else. It is not proposed when the device's deploy already
holds other lines not sent (deploy or resolve those first), when its intent already holds
dampening, or when the interface carries a `dampening` line with parameters a person chose.
**One hash** covers both the intent commit and its deploy: if either changes before it runs,
it is refused, naming both hashes.

**Its card** is the Needs attention item "A change to intent waits for a person: dampening on
<device> <port>", opened with **Review the fix…**: the program, the intent edit, how it is
verified, and how it is undone. **Approve and run** is refused, saying why, when the removal of
`dampening` (`interface.dampening`) is not measured on the device's platform, since that removal
is its rollback; and once the port has needed no bounce for **24 hours**, when the proposal has
lapsed (resolved by time; a later flap proposes it again).

**How it runs**, as the person who approved it:

1. `take`: the approved proposal, once.
2. `stops`: the kill switch, the mode, a halt, planned work, and the kind still proposed.
3. `rollback`: the removal of `dampening` measured on the device's platform, or nothing is
   done; its program (`interface <port>`, ` no dampening`, `exit`) is recorded.
4. `plan`: intent is patched again and its deploy planned; refused unless the one hash is the
   one you approved.
5. `intent`: the intent edit is committed as you, with your reason, the proposal's hash and its
   decision in the commit.
6. `apply`: the deploy runs as you, holding the device: the deploy's nine stages, its program
   recomputed from the committed intent and refused if it is not the one approved.
7. `verify`: after the deploy verified the line, with the device still held and its save held,
   `show interfaces dampening` must list the port. A read that does not list it rolls the device
   back by the deploy's own rollback, and the intent edit is put back as you. A read Mercury
   cannot interpret neither passes nor fails: the change is kept and called not verified. This
   read's interpretation is built from Cisco's documented output and not yet from a capture of
   a lab device, and the record says so.
8. `record`: the outcome on the device's **History**, kind Self-healing, and the incident
   closed.

**What it ends with.** Dampening deployed and verified, and the item leaves Needs attention; or
declined with your reason, recorded, nothing sent. Otherwise one item stays, "The approved
dampening of <device> <port>", until the port needs another bounce or 7 days pass: **rolled
back** (neither the device nor intent holds dampening); **not verified**; **NOT RESTORED** (which
halts the network's healing until a person lifts it); or **nothing was sent** (the intent edit put
back if it had been committed). Each of these is told to the team in the item's own words ([An
action's end, told](notifications#actions)); dampening deployed and verified is yours, and is
not told.

## What it never does {#never}

Self-healing never adds what intent does not hold, never acts on a device held by another
operation or in planned work, never changes a credential, never sends a line the policy did not
confirm, and never acts on what an AI analysis says: an analysis is advice for a person.
