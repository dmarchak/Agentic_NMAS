# Needs attention

The landing page answers one question: does anything need you?

## What it shows {#what-it-shows}

- **When nothing is wrong**, one line says so, and what was checked is one level down, each
  source with the age of its value.
- **When something is wrong**, one row per thing, worst first: what it is, which devices,
  since when, the cause, and the ONE action that deals with it. A source that did not answer,
  or whose value is older than it promised, is itself a row.
- **Never a fact with nothing to do.** Every row names something wrong and an action you can
  take. Something true that needs nothing, such as a new release being available, a lab
  startup file left by a retired device, or a check that missed a booting device once, is
  said under "What was checked", beside the source that found it, or on its own page.
- **Recent changes**: the last deploys and restores, from their receipts.

## The count in the sidebar {#count}

Beside "Needs attention" in the sidebar, on every page, is the number of rows this page shows
now, coloured by the worst of them: red for a critical row, amber for warnings only, grey when
every row is unknown. It is this page's own count, from the same rows, and it changes the
moment a row appears or clears, without a reload: it listens for everything that can move a
row, and it reads again at the moment a row clears by time (an approval expiring, a restart's
seven days). While live updates are stopped, or a source it counts is older than it promised,
it is drawn faded with a dashed outline, and its hover says it may be out of date; it catches
up when they come back. A "?" means the count could not be read, which is not the same as
nothing needing attention.

## Where the rows come from {#sources}

Background readers keep each source's value: job health (the host's scheduled checks), drift,
approvals, pending onboardings, rollback blocks, Grafana's alerts (a device's heartbeat
stopping is one), Oxidized freshness, integrations, reachability, routing adjacencies,
baselines, the remote's publication, the lab's startup files, unplanned device restarts (a crash file saved makes the row critical) and the app's own version. A
reader that finishes announces it, and the page redraws in place.

## How a row clears {#clearing}

Every row says, under its cause, how it leaves the page: "Clears when …". There are three ways:

- **The condition resolves.** Most rows: the source reads the thing fixed (a later drift check
  finds the device matching, a job's next run reads ok, a device answers again). Doing the
  row's action is how you make that happen; the row leaves at the source's next read.
- **A person acknowledges it.** For an event that cannot un-happen, such as an unplanned
  restart or the same line authorised again and again. See below.
- **Time.** An unplanned restart stays for 7 days if nobody acknowledges it; a pending
  approval expires after 48 hours (expiring executes nothing).

## Acknowledging an event {#acknowledging}

An unplanned restart, or a line authorised again and again, is something that happened, and
nothing will make it resolve. When you have looked into it, press **Acknowledge…** on the row,
say in a few words why it needs nothing more (what you found, or why it was expected), and
press **Acknowledge**. The reason is required (at least three words); it is recorded with your
name, how your identity was established and the time, and the row leaves the page.

- **An acknowledgement covers that one event.** A new restart of the same device is a new row;
  the same line authorised once more after you acknowledged it raises the row again.
- **The record keeps the event.** The device's History still shows the restart as unexpected,
  marked "acknowledged" with who and why.
- **A planned window cannot be declared afterwards to clear one.** A restart is planned only
  when the tool did it (its Reload) or was told beforehand (a planned-restart window). A window
  recorded after the tool saw the restart it covers is refused, unless it is marked as a
  correction with its own reason: a restart that really was planned and only recorded late.
  History then says the window was a correction, and why.
