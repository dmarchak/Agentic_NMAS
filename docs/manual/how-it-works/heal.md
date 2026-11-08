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
nothing to heal, and raises no "could not fix" item. One still flapping is judged as before.

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
4. `fresh`: both ends are read again, with the device's own route back to Mercury.
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
attention item; the team's notice of a bounce is not sent yet. Every other end is one item, "Self-healing's bounce of <device> <port>",
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
   route back to Mercury.
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
back if it had been committed).

## What it never does {#never}

Self-healing never adds what intent does not hold, never acts on a device held by another
operation or in planned work, never changes a credential, never sends a line the policy did not
confirm, and never acts on what an AI analysis says: an analysis is advice for a person.
