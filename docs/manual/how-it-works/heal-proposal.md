# Approve or decline a self-healing proposal

Self-healing heals some departures from intent by itself (Tier 1, Auto). A fix that takes
effect only through something rollback cannot undo, such as an OSPF router-id that needs its
routing process reset, is never automatic: it is **proposed** (Tier 2, Propose). Mercury records
the proposal with its program and hash and sends nothing. A person approves it by that hash (a
reason optional, unless a line of it needs one), or declines it with a reason. A network's Self-healing tab chooses which Tier 2
kinds are proposed ([Self-healing](settings#self-healing)).

![Approve a self-healing proposal: self-healing found a fix that needs a person and recorded it with its program and hash, sending nothing; its card on Needs attention says what happened, whether it needs you, the fix, what it affects, how Mercury checks it worked and what happens if you don't, the program one press away; you approve by the proposal's hash, a reason optional unless a line needs one, or decline with a reason, which sends nothing; approved, a job takes the proposal once and, holding the device as you, reads it again, recomputes the program and refuses if its hash moved, applies it through the deploy pipeline, then sends the measured reset and reads the adjacencies back; a failure before the reset puts the change back; the outcome is recorded and History shows it.](diagrams/heal-proposal.svg)

## The proposal's card {#card}

A proposal waiting is a **Critical** row on **Needs attention**. Its line says what changed on
the device and that a fix needs your decision, for example "edge1: in router ospf 1,
“router-id 192.0.2.16” was changed to “router-id 192.0.2.14”. Mercury has a fix that restarts
OSPF on edge1: it needs your decision". **Review the fix…** opens the row to its card. The card is read
from Mercury's own records, never from the device. It answers four questions, in order, in
plain words:

- **What happened.** What Mercury holds about the change, each fact at its time: who made the
  change (as the configuration line named them) and what it changed, then each symptom it
  caused. Where Mercury holds both ends of a cause, a **likely cause** follows the facts,
  labelled as a hypothesis. Both ends means a change on an interface and a symptom on that
  interface after it, or a router-id the change set that a duplicate router-id report names.
  For example: "Likely cause (a hypothesis, not checked): this ACL drops OSPF on Gi2, so edge1
  lost its OSPF neighbour edge2". Mercury never guesses a link it does not hold.
- **Does it need you? Yes**, and why. A process reset briefly drops all of the device's
  neighbours, so a person decides when.
- **The fix Mercury proposes**, and **What it affects**. What affects covers what the reset
  drops and how long the adjacencies took to form again where it was measured ("back within
  about 6 s"). It also says what the reset does not change.
- **How Mercury checks it worked.** Each check is listed. A check Mercury does not make yet
  says **can't tell**, never a pass. The card also says what happens if a step fails before
  the reset: Mercury puts the change back, and a reset cannot be undone.
- **If you don't.** The device keeps the change, the symptom stays, and the proposal is
  withdrawn if the device changes again.

Then come who proposed it and when, and each reason it would be refused now (**Not
confirmable**), such as a reset not yet measured, the kill switch, a halt or planned work.
Approve is drawn disabled with that reason. **Show the commands** opens the exact lines inline,
with the reset's command and where its prompt was measured. **Details for the record**, closed
until you open it, holds the proposal's and the incident's ids, the proposal's hash that Approve
sends, the program's hash, the fix type and tier, the policy, the decision's words, what raised
it and the steps approving runs.

**Times** are drawn in your browser's time zone, with UTC on hover. The record's own times,
under Details for the record, are UTC.

**In dry run, approving still sends.** Dry run holds only what self-healing would do by itself.
A proposal is a person's decision whatever the mode, so the card says above Approve: "Watching
only on <network> (dry run): Mercury sends nothing by itself. Approving this sends it."
Decline it if you only want the record.

## Approve {#approve}

Press **Approve and run on <device>** (a verified person's; on a security control's proposal
it reads **Remove it (back to intent)**, below). A reason is optional. It is required, of three
words or more, when a line of the fix needs a stated reason: a dangerous line or a removal. The card's Reason field says so. A reason you do give is held to that shape.
Approving is refused, with nothing taken or sent, when:

- you are not a verified person;
- a reason is needed and missing, or the one given is short;
- the hash is not the one the card drew (the refusal names both);
- the proposal was taken already;
- its reset is not measured;
- a stop applies.

Otherwise the card says "You approved it. Mercury is applying it on <device> now, recorded as
approved by you", with the job under Details for the record, and the row leaves Needs
attention. The job runs as you:

1. `take`: the proposal is taken once; a second approval is refused by name.
2. `stops`: the kill switch, the mode, a halt, planned work and the kind proposed are checked
   again.
3. `read`: the device is read again.
4. `plan`: the program is recomputed from that read and its hash compared; a moved hash sends
   nothing and closes the proposal.
5. `authorise`: each line the CI gate flags carries your reason, in the hash and the receipt.
6. `apply`: the program is applied as you, holding the device, through the deploy's nine
   stages.
7. `intent`: each fixed unit is checked at intent, or what landed is undone.
8. `reset`: the measured process reset is sent on the same session, only its measured prompt
   answered, and the neighbour table read until the adjacencies form again. A reset not made
   puts the change back.
9. `saved`: saved to startup once verified, the device released.
10. `golden`: the device is read again against its new golden.
11. `symptom`: the symptom is read again.
12. `record`: the outcome is recorded with your name and reason, and the incident closed.
    History shows each step on the device's History tab.

## Decline {#decline}

Type a reason, then press **Decline**. Nothing is sent. The decline is recorded with your
name and reason, the incident is closed, and the row leaves Needs attention. A later check
may propose again.

## A security control: remove it or keep it {#keep}

A security control added or changed outside intent (routing authentication or a key chain, an
ACL or its application, AAA, crypto or SSH, an SNMP restriction, control-plane policing, port
security or 802.1X, a line's `transport input`) is never removed by self-healing on its own: it
may be the first half of a rollout whose far end is not configured yet, or a control an auditor
asked for. Its proposal names the lines (masked) and offers two answers, each yours:

- **Remove it (back to intent)**: the proposal's approval, as above: the measured removal, by
  its hash, with your reason. A removal not yet measured on the device's platform is not a
  proposal: the row says self-healing cannot fix it yet and names the probe.
- **Keep it: add it to intent**: opens the device's intent editor (its Intent tab), where you
  add the lines and commit as you; nothing is sent to the device. Once intent holds them they
  are no longer a departure: decline the proposal with your reason, and an approval after it is
  refused at its plan step.

An ACL and the line applying it (an `ip access-group` on an interface), or any definition only
that one added line uses, are one fix: removed together, or kept together. A missing security
control is put back as any missing line is. A network may also let Mercury put back a one-sided
security change that broke an adjacency by itself (`heal_security_revert_adjacency`, off by
default; [Self-healing](heal)).

## Withdrawn {#withdrawn}

A proposal is bound to its program's hash and to the device as it was read when it was made.
While it waits, self-healing reads the device again once a grace period has passed since its
last read (2 minutes on a network marked lab, 15 otherwise), and at once when a configuration
change on it is seen. Each of these reads changes nothing on the device:

- the device is back at its golden, which matches its intent: the proposal is **withdrawn**,
  its incident closed, and the row leaves Needs attention;
- the device departs from its golden differently from the way it did when the proposal was
  made: the proposal is **withdrawn and made again**. Its incident is watched again from the
  device as it is now, and once its grace period settles, the decision makes a new proposal
  (if one is still needed), a new row of its own;
- anything else (the same departure, or a read that could not be made) leaves it waiting.

Each withdrawal is recorded in the network's heal decisions and on the device's History,
naming the read and the state the proposal was bound to. A withdrawn proposal's card says it
was withdrawn and why, and approving it is refused, naming the hash you confirmed and both
states. Nothing is sent.

## Lift the halt {#halt}

Self-healing on a network **halts** when a guard says it must stop until a person looks: the
same fix twice within the repeat window, more heals in an hour than the policy allows, or a
heal that was rolled back or failed after sending. Self-healing then heals nothing on that
network, makes no dry-run records and cannot run an approved proposal. The halt is a Critical
row on **Needs attention**: "Self-healing halted on <network>: <why>", naming its guard and
both operands. Read why: **Open the incident** opens the device's History, where the heal's
steps are, and **Edit <device>'s intent…** opens its Intent tab, for a line that belongs in
intent. Then press **Lift the halt…** on the row's line (or open the row), type a reason of three
words or more, and press **Lift the halt** (a verified person's). Pressing
Enter in the reason field sends nothing. Lifting sends nothing to a device. The lift is recorded
with your name and reason in the network's heal decisions, self-healing runs under its policy
again from its next check, and the row leaves Needs attention. The lift is refused, naming
both operands, when you are not a verified person, when the reason is short, or when the halt
is no longer the one in force (someone lifted it first, and the refusal names who).

The installation's kill switch, **Stop self-healing everywhere**, is a row of its own, "Self-
healing is stopped everywhere". Its way out is **Resume self-healing…** on a network's
Self-healing tab, as previewed, with a reason ([Self-healing](settings#self-healing)).
