# Check drift

The drift check reads every device in the network and compares its running configuration with
its committed golden. It changes nothing on any device and nothing in the repository: it
records what it found, names every device it could not check, and queues one item for each
device that has drifted, for a person to resolve. What drift is, and what does not count, is
on [Drift](drift).

![The drift check: the inventory is the population; each device is skipped with a reason, read once, or found unreachable; each read is compared with the committed golden; a drifted device queues an approval item; the run is recorded and every device lands in one bucket.](diagrams/drift-check.svg)

## The run, step by step

The same run serves the schedule and Check now, on the Drift checks card of Settings ›
Installation › Diagnostics. A run is for ONE network, named, and the schedule runs every
network on its own: each has its own next run (its last run plus the interval), its own on/off
switch and its own record, whichever network the tool is showing. The card has a row per
network, and its Check now and Turn off or Turn on act on that row's network.

1. **Take the population from the inventory.** Read: the network's inventory, every device in
   it. Sent: nothing. Recorded: nothing. The inventory,
   not the golden store, is what is checked, so a device without a golden is named instead of
   being absent. An empty inventory ends the run with "Inventory is empty, nothing to check".
2. **Set aside what cannot be checked.** Read: whether the device is stale, and its golden as
   committed in git. Sent: nothing. Recorded: the device and its reason in the run's
   "not checked" list. Three reasons: no longer in NetBox for this list (a stale device of a
   NetBox-sourced list, which nothing acts on); the golden is refused (a file nothing
   committed, or a commit with no `Source:`); no golden saved yet.
3. **Read the device.** Read: one `show running-config` per device, up to six devices at
   once. Sent: that one show command, nothing that changes the device. Recorded: nothing yet.
   The read is judged before it is compared: output that came back stitched together (a
   second `end`, a prompt, an echoed command, another device's hostname, or far larger than
   its golden) is refused as unreliable, and that session is closed and never read again. A
   device that cannot be read, or whose read is refused, goes to the run's unreachable list
   with the reason.
4. **Compare with the golden.** Read: nothing new. Sent: nothing. Recorded: nothing yet. Both
   sides lose the lines that change with nobody changing anything, and the device's own
   self-signed certificate (see [What counts as drift](drift#what-counts)); the rest is
   compared line by line, in order.
5. **A clean device closes what is stale.** Read: the approval queue. Sent: nothing.
   Recorded: every pending drift item for that device, queued by an earlier run, is withdrawn
   with the reason (this run found the device at its golden under the current rules). A
   withdrawn item is neither approved nor rejected.
6. **A drifted device queues one item.** Read: the approval queue. Sent: nothing. Recorded:
   one pending approval item (`update_golden_config`) naming the device and carrying the diff
   (its first 200 lines). If the device already has a pending drift item, no second one is
   queued.
7. **Account for every device.** Read: nothing. Sent: nothing. Recorded: nothing yet. Each
   device lands in exactly one bucket, and a device that landed in none is reported as a
   defect in the checker, never dropped from the total.
8. **Record the run.** Read: nothing. Sent: nothing. Recorded: the run's result and its time
   in the list's drift state, which the Drift checks card, Needs attention and the device page
   read.

## The buckets {#buckets}

Every device in the inventory ends the run in one of these:

- **Clean**: read, and the same as its golden.
- **Drifted**: read, and different from its golden, with the number of diff lines.
- **Not checked**: stale, golden refused, or no golden, each with its reason.
- **Unreachable**: the read failed or could not be trusted, with the reason. The device may
  have answered: a refused read is listed here too, so read the reason.

The summary always states the coverage, "checked N of M", where N counts clean and drifted
devices and M is the inventory. "All 7 checked device(s) clean (checked 7 of 9)" is a
different sentence from "checked 9 of 9", and the other two are named after it. A regenerated
self-signed certificate is named in the summary as not drift.

## Scheduling {#schedule}

- **The interval** is one setting for the installation, 4 hours by default, set by the Drift
  checks card's Every and Save. Saving it rebuilds every network's next run from its last run
  and the new interval, and the change is recorded with who made it.
- **The first run** after the tool starts, on an install that has never run a check, is 5
  minutes after start. After that, the next run is the last run's time plus the interval, so
  the schedule survives a restart.
- **The next run's time is kept in memory.** Editing the state file does not move it; Check
  now does.
- **Check now** starts the network's check at once, in the background, and the card redraws
  when the run is recorded. It refuses while a run of that network is already in progress, by
  anyone and from any process (the scheduled run, another person's Check now, a script),
  naming when it started, what started it and which process; one run per network at a time.
  A row whose run another process holds reads "checking now" and says who. A scheduled run
  that finds one in progress tries again a minute later.
- **An unreadable state file pauses the schedule.** The network's row reads "unreadable" with
  why; nothing is written over the file (a refused write keeps a copy beside it), and the
  schedule resumes once the file is readable again or moved aside. A run whose result cannot
  be recorded is not shown as done: the row stays "unreadable".
- **Each network is checked on its own.** Its state (last run, switched off or on) is kept per
  network, and the schedule runs every network that is due, whichever network the tool is
  showing.

## Switching it off is recorded {#disable}

Each network's row on the Drift checks card has Turn off or Turn on. Switching it off records
when and by whom (the verified person, when there is one), in the drift state and in the
installation's settings record, and the row shows who and when. While it is off, Needs
attention carries a row saying so, naming who switched it off, with a link to the card.
Switching it back on schedules the next run one interval from then.

## What the queue does with a drift item {#queue}

- **Capturing the device closes its item**: its Needs attention row offers
  **Capture <device>…**, which opens the Capture card on the device's page, where a capture reads the
  device again now and records nothing until you confirm (see [Capture and Save All](capture)),
  and **Deploy intent to <device>…**, which puts intent back instead. The queued diff is what the check saw at the
  time, context only, never sent or recorded. (Today's Approvals tab, with its Approve and
  Approve all, left with the AI family on 2026-10-14.)
- **An item is withdrawn** when a later run finds the device clean, or when a golden is
  recorded for the device (a capture, Save All or a deploy). Recording a golden also marks that
  device clean in the stored run, saying by what and when, without reading it again.
- **An item expires** 48 hours after it was queued. Expiry never executes anything.

Restoring the device from its golden is the other resolution, and it is not queued: it is on
the device page (see [Two ways to resolve drift](drift#resolve)).

## Where the result shows

- **Needs attention** draws one row per device the last run did not clear: drifted (danger,
  with a queued item folded into it), not checked (warning, with what to do), unreachable
  (unknown). It also draws the checker's own state: switched off, never run, a failed run, or
  a last run older than two intervals.
- **The device page's Overview** shows the Drift row for that device from the same stored run.
- **The Drift checks card** (Settings › Installation › Diagnostics) shows each network's last
  run, its summary with the coverage on hover, the next run and the schedule.

No page reads a device to draw a drift row: every row comes from the stored run.

## What the check does not do {#not}

- It sends nothing that changes a device, and writes nothing to the repository.
- It never compares with intent: a clean device can still depart from its intent.
- It never resolves drift. Capture or restore is a person's choice, previewed and confirmed.
- It does not record since when a device has differed, only when the check saw it.
- A run does not check devices outside the network it names; the schedule runs each network
  on its own.
