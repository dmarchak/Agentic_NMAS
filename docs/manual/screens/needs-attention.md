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

**Credentials** (hourly, metadata only, never a value): a credential with an expiry is a
warning 30 days before it expires, a danger row 7 days before, and a danger row as soon as it
has expired. One expiring more than a year out has no row. Where each expiry comes from:

- **NetBox's API token:** NetBox shows it.
- **Proxmox's TLS certificate:** read from the certificate itself.
- **Grafana's and Proxmox's API tokens:** the expiry declared for each in Settings →
  Integrations, because neither token can read its own. "never" is a valid declaration.

An expiry that could not be read is an **Unknown** row, never a warning: a warning claims a danger
the reader has seen. A device's login credential or an SNMP community older than 180 days is a warning
naming Rotate. Each row says where the credential is renewed and where its new value goes. An
integration that **refuses** the tool's credential (a 401 or 403 to its probe, every minute) is
a danger row of its own, never "down".

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

### A chronic alert, within its band {#acknowledging-a-chronic-alert}

An alert that fires on one series nearly all the time (a port that always discards a little,
for a known reason) stops meaning anything, and a real change on that port would look the
same. Its row offers **Acknowledge…** too, with a difference: the acknowledgement holds only
within the series' measured band.

- **When you acknowledge it**, the tool measures the series' 95th percentile over the last 7
  days (at 5-minute steps, from the alert rule's own query without its threshold) and records
  it with your reason. If it cannot measure the band, it refuses and says why.
- **While the value stays at or under that band**, the row is not listed, and the
  acknowledged list beside the table says "within its band", with the value and the band.
- **When the value rises above the band**, the row comes back. It names who acknowledged it,
  the band and the value now, so a change on a chronic port is still seen.
- Only an alert on one series, whose rule is a Prometheus query ending in a threshold, can be
  acknowledged this way. Any other alert clears when it stops firing.
