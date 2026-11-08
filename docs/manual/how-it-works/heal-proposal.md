# Approve or decline a self-healing proposal

Self-healing heals some departures from intent by itself (Tier 1, Auto). A fix that takes
effect only through something rollback cannot undo, such as an OSPF router-id that needs its
routing process reset, is never automatic: it is **proposed** (Tier 2, Propose). Mercury records
the proposal with its program and hash and sends nothing. A person approves it by that hash
with a reason, or declines it with a reason. A network's Self-healing tab chooses which Tier 2
kinds are proposed ([Self-healing](settings#self-healing)).

![Approve a self-healing proposal: self-healing found a fix that needs a person and recorded it with its program and hash, sending nothing; its card on Needs attention shows the program, the measured process reset it needs, what that affects and the proposal's hash; you approve by that hash with a reason, or decline with a reason, which sends nothing; approved, a job takes the proposal once and, holding the device as you, reads it again, recomputes the program and refuses if its hash moved, applies it through the deploy pipeline, then sends the measured reset and reads the adjacencies back; a failure before the reset puts the change back; the outcome is recorded and History shows it.](diagrams/heal-proposal.svg)

## The proposal's card {#card}

A proposal waiting is a row on **Needs attention**: "A fix waits for a person on <device>".
**Review the fix…** opens the row to its card, read from Mercury's own records (never the
device):

- what approving does and on which device: the program as recorded, masked, and the process
  reset it needs, with whether that reset is measured on the device's platform;
- **Expected effects**: what the reset drops (every adjacency of the process) until it forms
  again;
- **Verify reads**: the deploy's verify, then the neighbour table until the adjacencies formed
  before form again, within about 2.5 times the measured settle time;
- **Rollback**: the change is put back if a step fails or the reset is not made; a reset
  cannot be undone;
- **Proposal hash**: what Approve sends, bound to the network, the device, the decision, the
  program's hash and the reset's command;
- each reason it would be refused now (**Not confirmable**), such as a reset not yet measured,
  the kill switch, a halt or planned work. Approve is drawn disabled with that reason;
- **What Mercury found and tried**, and **What approving runs**, one level down.

**In dry run, approving still sends.** Dry run holds only what self-healing would do by itself;
a proposal is a person's decision whatever the mode, so the card says, above Approve, "This
sends, although <network> is in dry run", naming what runs and on which device. Decline it if
you only want the record.

**Check drift now on <device>** reads the device against its golden first, changing nothing
([Check drift](drift-check)).

## Approve {#approve}

Type a reason of three words or more, then press **Approve and run on <device>** (a verified
person's). It is refused, with nothing taken or sent, when you are not a verified person, the
reason is short, the hash is not the one the card drew (the refusal names both), the proposal
was taken already, its reset is not measured, or a stop applies. Otherwise the card says it was
approved and names the job, and the row leaves Needs attention. The job runs as you:

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
