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
   watching, and nothing new starts.
2. `lock`: it holds the network, one pass at a time across Mercury's processes.
3. `judge`: it judges each incident's grace period.
4. `read`: when a read is due, it reads the device, the same read and comparison as **Check
   drift now** ([Check drift](drift-check)): the first at once, the second a grace period later
   (2 minutes on a network marked lab, 15 otherwise). A device that changes again restarts its
   grace period, so a person's change in progress is never healed half-way.
5. `members`: a device attached to the incident (its far end, say) is read once, and never
   healed on its own.
6. `settle`: an incident the two reads agree on is handed to the decision.
7. `proposals`: each proposal still waiting for a person has its device read again, and is
   withdrawn when it no longer fits ([Withdrawn](heal-proposal#withdrawn)).

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
8. `symptom`: the symptom that opened the incident is read again.
9. `saved`: once verified, the running configuration is saved and the device released.
10. `golden`: the device is captured and read again against its new golden.
11. `record`: the outcome is recorded and the incident closed.

A failed verify rolls back what landed, and **halts** the network's healing until a person
lifts it ([Lift the halt](heal-proposal#halt)). A configuration healed whose symptom remains is
amber, "symptom remains", never green.

## The records {#records}

Every incident is one row on **History**, kind Self-healing, its line the newest outcome with
the mode on it ("dry run" is never read as Auto), opening to every step and its result, the
program (masked) and its hash, and the records it wrote: the deploy receipt, the golden commit
(`Source: heal_to_intent`, `Actor-Verified: policy`), the golden read again, the change record
and the NetBox journal entry. A healed incident is History and a notice, never a Needs attention
item. The network's team is told as its Self-healing tab chooses ([Notifications](notifications)).

## Dry run: Right or Wrong {#mark}

In dry run nothing is sent; each would-heal is a record for a person to judge. It is an item on
**Needs attention**, "Self-healing: dry run on <network>: it would have healed <device>",
carried by the device's drift item, for up to 7 days. Open the record on the device's
**History** (or History, kind Self-healing): under its steps, **Was this the right fix?**

- **Right** records that what it would have done was right, with your name.
- **Wrong…** opens a reason: type why it was wrong (what it would have broken, or the fix that
  was right) and press **Mark it wrong**. Pressing Enter in the reason sends nothing.

Each is a verified person's, sends nothing to a device, and is answered in place. The mark is
recorded in the network's heal decisions; marked again, the newest mark counts, and every mark
stays. The marks are counted per fix kind as the dry run's false-positive rate, which a network's
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

**None of these actions is built yet**: a policy cannot allow one, and each is refused by name
("not built yet: H20"). What runs now is the **flap record**: each time the network's syslog is
read, every `%LINK-3-UPDOWN` and `%LINEPROTO-5-UPDOWN` line is recorded as a transition of its
interface at the time Mercury received it, never by the device's clock, for networks whose
self-healing is on. A link and its line protocol going down together count once. A flap is
**A flap: transitions of one interface within** on the Self-healing tab (3 in 10 minutes by
default); the record keeps an hour.

## What it never does {#never}

Self-healing never adds what intent does not hold, never acts on a device held by another
operation or in planned work, never changes a credential, never sends a line the policy did not
confirm, and never acts on what an AI analysis says: an analysis is advice for a person.
