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
