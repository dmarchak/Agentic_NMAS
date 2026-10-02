# Approve a queued action

The approval queue holds actions the tool proposed and will not take on its own. The drift
check queues one for each device whose running configuration has moved from its golden; the
AI agent can queue one too. Approving an item never changes a device or the record by
itself: it opens the operation that does, with a preview computed now, and the work happens
only when you confirm that preview.

![An item waits in the queue. Approving it opens the capture preview or the restore preview for its device, computed now; the item closes only when the confirmed operation records the device. The queued diff travels beside the preview as context and is never sent.](diagrams/approvals.svg)

## What can be queued {#kinds}

- **Record the running configuration as the golden** (`update_golden_config`). Queued by
  the drift check, one item per drifted device, with the diff it saw. Approving it opens a
  [capture](capture) of that device.
- **Put the device back to its golden** (`revert_to_golden`). Queued only by the AI agent.
  Approving it opens a [restore](restore) of that device to its golden at HEAD.

A second item of the same kind for the same device is not added while one is pending.
Every item carries what the proposer saw, when it saw it: its description, its context and
its diff.

## Approving an item

1. **Approve** (as you). Read: the queue. Sent: nothing. Recorded: the item is marked
   approved with you as the person who decided. Only a verified person may approve.
2. **Refuse a device that has left NetBox**. Read: whether the device is stale on a
   NetBox-sourced list. Sent: nothing. Recorded: the item goes back to pending with "Last
   attempt failed" and the reason. A device that vanished from NetBox is inert: nothing
   may act on it.
3. **Hand off**. Read: nothing. Sent: nothing. Recorded: the item goes back to pending,
   reading "Awaiting confirmation". Marking it approved here would have the queue claim a
   change nobody has made. The tool opens:
   - for a drift item, the capture preview of that one device: it reads the device NOW and
     shows how its golden would change and how it compares with committed intent;
   - for a revert item, the restore preview of that device at HEAD, with the queued diff
     drawn above it as "what the agent saw", context only, never what is sent.
4. **Confirm the operation**. Read: what that operation reads (the device, for both). Sent:
   for a restore, the program you confirmed; for a capture, nothing. Recorded: what that
   operation records, as you. The confirm is bound to that preview's own hash, so the
   queued diff, computed when the drift was noticed, never reaches a device.
5. **Close the item** (`mark_done`). Read: the operation's outcome per device. Sent:
   nothing. Recorded: the item is closed as approved, with a note of what completed it.
   A capture closes the item only for a device it recorded (captured, or read and found
   unchanged). An item whose device moved, could not be read or was busy stays pending.

**Today, a revert item does not close as done.** Confirming any restore first rejects
every pending revert item on the list, including the one that opened it, so after a
successful restore that item reads rejected, with no reason on the item, and the result
says the queue item was not closed. The restore itself is unaffected.

## Rejecting an item

1. **Reject** (as you). Read: the queue. Sent: nothing. Recorded: the item is marked
   rejected with you as the person who decided. Nothing is done.

## Approve all {#approve-all}

Approve all approves nothing by itself. It collects every pending drift item's device into
ONE capture preview, where each device is read now and confirmed by its own hash, and each
item closes only when its device is recorded. Revert items are named for individual
review, because each is a restore of one device.

## How an item ends without anyone approving it {#ends}

- **Withdrawn.** A pending drift item is withdrawn, with its reason and what withdrew it,
  when a newer golden records its device (any capture, Save All, deploy or restore) or a
  later drift check finds the device at its golden. The diff it carries no longer
  describes the device. Withdrawn is its own state: nothing was approved, and nobody
  refused it.
- **Expired.** An item left pending for 48 hours is marked expired. Expiry never runs
  anything.

## What the queue does not do {#not}

- Nothing in the queue sends to a device or commits. The capture, the restore and their
  confirms do, each recorded as the person who confirmed.
- The AI agent and the drift check only add items. Neither can approve one.
- The queued diff is never an input to anything that runs. It is shown masked.
