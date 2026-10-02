# Approvals

The approval queue: what the tool has proposed and is waiting for a person to decide, with
the drift check that fills most of it. Today it is a tab of the main page; the redesign
folds it into [Needs attention](needs-attention), where a drift item already sits on its
device's drift row. What approving does is in [Approve a queued action](approvals).


## Where it is {#where}

On today's main page, the **Approvals** tab. Its badge counts the pending items and is
refreshed every 30 seconds whichever tab is open; while the tab is open, the list is
refreshed with it. The queue shown is the active list's.

## The drift check panel {#drift}

At the top: the drift check's state, when it last ran, how often it runs, an **Enabled**
switch and **Check Now**. It is here because a drift check is what queues most items. It
works whether or not the AI agent is enabled. See [The drift check](drift-check).

## The items {#items}

Pending items, oldest first. Each card shows:

- **State**: pending, approved, rejected, expired or withdrawn.
- **What was proposed**: *Update Golden Config* (record the device's running configuration
  as its golden) or *Revert to Golden* (put the device back to its golden).
- **When** it was queued, and for a pending item when it **expires** (48 hours after).
- **The device**, by name and address.
- **The description and context**: what the proposer said, and what has happened to the
  item since, such as "Awaiting confirmation" after you approved it, or "Last attempt
  failed" with the reason.
- **View diff**: the diff the proposer saw when it queued the item, with every secret
  masked. It is context only: approving computes a fresh preview, and the diff is never
  what is sent.

A pending item has **Approve** and **Reject**. Approve opens the capture or restore preview
for that device; nothing is recorded until you confirm it there. A resolved item shows its
state and when it was resolved.

## The controls {#controls}

- **Show resolved**: lists every item, resolved, expired and withdrawn included, newest
  first. It shows the 50 newest, and does not say when there are more.
- **Approve All**: opens ONE capture preview for every pending drift item's device and
  names the other items for individual review. It approves nothing by itself. It is shown
  only while the AI agent is enabled and more than one item is pending.
- **Refresh** reads the queue again.

## What it does not show {#not}

- Who approved or rejected an item, and why a withdrawn item was withdrawn: both are kept
  in the queue and not drawn here.
- When nothing is pending, the empty message also says every device is up to date. The
  queue cannot know that: a device the drift check could not read, or a check that is
  switched off, queues nothing. The drift check panel above says what the last check
  found.
