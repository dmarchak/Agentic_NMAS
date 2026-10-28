# Needs attention

The landing page answers one question: does anything need you?

## What it shows {#what-it-shows}

- **When nothing is wrong**, one line says so, and what was checked is one level down, each
  source with the age of its value.
- **When something is wrong**, one row per thing, worst first: what it is, which devices,
  since when, the cause, and the action that deals with it. Most rows have one; a drifted
  device's row has two, which mean opposite things (below), and so has a rollback's
  (**Revert intent…** or **Retry with a reason…**). A source that did not answer, or whose value is older than
  it promised, is itself a row.
- **Every device is named with its network** ("edge1 in Branch"), because some sources watch
  every network: job health, Grafana's alerts and reachability. A name two networks both hold
  is said as either ("edge2 (Branch or Default)"). Its **Open <device>** button, and an action
  that is an address, open the device in its own network when that is known; for a name two
  networks hold, it opens in the network you are looking at.
- **The sources kept per network** (drift, approvals, pending onboardings, rollback blocks,
  deploys, baselines and repeated authorisations) are the network the page names: its address,
  else your own choice of network. A network with no drift run says "No drift check has run
  yet", never another network's run.
- **One cause is one row.** A device whose configuration has no heartbeat is its one "not
  monitored" row; Grafana's "no heartbeat rule" row leaves it out, and says so.
- **Never a fact with nothing to do.** Every row names something wrong and an action you can
  take. Something true that needs nothing, such as a new release being available, or a
  check that missed a booting device once, is
  said under "What was checked", beside the source that found it, or on its own page.
- **Recent changes**: the last deploys and restores, from their receipts. It reads itself again
  when a deploy or restore finishes, so a page left open shows the new one without a reload.

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
stopping is one), integrations, reachability, routing adjacencies (as Prometheus reads them, and
as the devices log them),
baselines, the remote's publication, unplanned device restarts (a crash file saved makes the row critical) and the app's own version. A
reader that finishes announces it, and the page redraws in place.

The other rows, each with its own cause and action: deploys that failed or were verified and
not saved to startup; a deploy that landed and was saved while verify could not read back some
of the lines it sent, a warning naming the lines (read them in the device's golden on its
History tab: acknowledge the row with that reason when the device prints them in another
form, or plan the deploy again when they are absent; a later deploy that misses a line raises
it again); operations interrupted while they held a device (the process ended
mid-run); a device's SSH host key that changed (**Re-key…** on its page), and the new keys a
planned window kept; the records database's stores that do not match or do not answer; the
scheduled rotation's timer, stopped on a failure; templates behind the shipped version in a
way that drops lines; the log redaction found unhealthy; the CI verdict on the running commit,
and a pushed release whose CI failed; host steps owed; a NetBox-sourced network's unreadable
inventory; a rollback's record; pending onboardings (overdue, or still holding a staged
credential); Grafana's rule groups that stopped evaluating, and rules that read no data; the
fleet's heartbeat stopping at once (one row, not one per device); the routing adjacencies
Prometheus reads (a link down, adjacencies it cannot measure, or its read failing); and drift
(a drifted, skipped or unreachable device, a check that is off, failed, never ran or is
old); and SDN (an SDN loop a restart stopped; one row per incident awaiting a person, red
once it has gone unanswered past its network's escalation threshold, 15 minutes unless set,
and saying no on-call integration exists to notify; a response's flows missing before their
hard timeout; and a network whose SDN controller is not answering; see
[SDN](sdn#controllers)). Each network's own Prometheus has its own row comparing what it scrapes with its
networks' inventories ("…, for <network>'s Prometheus"; see [Settings](settings#network)),
and each network's own Grafana its own alerts and token expiry.

**Adjacencies logged down.** Prometheus reads each device's routing tables once a minute, so
an adjacency that drops and comes back between two reads never shows there. The device's own
log does show it. Mercury reads the routing adjacency changes every managed device logged
(`%OSPF-5-ADJCHG`, `%OSPFv3-5-ADJCHG`, `%BGP-5-ADJCHANGE`) and raises one row per adjacency.
The row names the logging device, the protocol, the neighbour, how many times it went down in
the last day, the last time and the reason the device gave.
- A drop inside a planned restart's window, or around a deploy to that device, is counted under
  What was checked and never raised.
- An adjacency that flaps for a known reason can be acknowledged within its band: the highest
  daily count of the last week. It stays quiet while the day's count stays at or under that,
  and returns, saying so, when it goes above.
- With no drop for a day, the row clears.

Oxidized is retired (2026-10-08), and its freshness check with it: nothing here compares
Oxidized's copy. A change made on a device outside Mercury is raised by the drift check, which reads each
device's running configuration against its golden on the interval set for it (four hours
unless changed). A drifted device's row carries both answers: **Capture** records what the device
holds as its golden (the change was wanted), and **Deploy intent** puts its committed intent back
(it was not); each opens its card on the device's page, with its preview and confirm.

**An operation re-reads what it changed, at once.** Each reader runs on its own interval, and
an operation that changes what a reader reports runs that reader again as soon as it is done:
a Save All re-reads the baselines, a rotation or an onboarding re-reads job health (the
rotation's safety, the break-glass record) and credential health, a break-glass export or drill
re-reads job health, a persist re-reads the save record, an acknowledgement re-reads its alert.
So a row the operation resolved clears for everyone looking, without waiting for the next
cycle. A rotation still running raises no "persistence not attempted" row: that is the moment
between its rotate and its persist; the row appears only if the rotation ends there. Every row
says how old the reading it stands on is ("read 2 min ago"), and a Save All that would record
the same state as a baseline just taken says so in its preview, with when and by whom.

**Baselines** (the newest `Baseline:` decision in the network's history, and the stored
baselines' usability): a commit that did not earn a baseline is a row, with its commit and
time. Its remedy depends on why. A deploy or restore that did not cover the network (devices
"not targeted", and nothing else) is a partial operation's decision, not a denial: the row
says so ("the last commit (a deploy to edge2) did not cover the network, so it earned no
baseline: Save All takes one"), and Save All alone takes one. A Save All denied because a
device departs from its intent names each departure, and Save All will be refused again until
each is resolved, by changing the device or the intent. When no stored baseline can be
re-applied (each predates a credential rotation, or is withdrawn), one row says so and carries
whichever of the two the last decision was. The row clears when a later decision earns a
baseline.

**A source that has not been read within its promise** is a row of its own: each reader says
how often it reads, and when a source's value is older than that, the row names the source, how
old its value is and how often it is promised, because what it shows may no longer be true.
Open Job health to read why its reader has not run; the row clears when the source is read
again in time. (Drift judges its own: "the last drift check is old".)

**NetBox-sourced networks:** when a network takes its devices from NetBox and its last refresh
could not read them (NetBox did not answer, or answered its filter with an error, as it does
when the site the filter names was deleted), the network keeps the last good list, marks
nothing gone, and one row says so: the network, its filter, NetBox's answer, and the devices
kept with the time of the last good read. Fix the filter on Settings › the network ›
Network, or restore what it names in NetBox; the row clears when a refresh reads NetBox again.

**NetBox behind a device's committed configuration.** Onboarding records a device in NetBox
once, from its first golden; a deploy changes the golden and never writes NetBox. So for each
managed device of a network that is in NetBox, a reader compares the committed golden with
what NetBox holds (every 5 minutes, and at once after an import, an onboarding's Verify, an
adoption, or a deploy or Save that commits a golden). A device holding more than NetBox is one
row: "NetBox holds less than edge1's committed configuration: 1 interface, 2 addresses, 1
cable to add". It counts the interfaces and the IPv4 and IPv6 addresses the import would add,
and the cables it would make from LLDP (a link both ends report between two managed devices).
Its cause names each one. Its action, **Import into NetBox…**, opens the device's NetBox tab,
whose **Import into NetBox…** previews the import of that device alone. While NetBox writes
are off the row says so, and where they come on. The row clears when the import lands and the
reader finds NetBox holding the golden. A network nobody imports into NetBox (no site and no
device record there) is not compared.

**Intent laid out by hand.** Change it in words and bulk intent change a device's intent by
rewriting it through Mercury's serialiser, so they refuse a document whose comments or layout
that would drop. A reader checks every network's committed intent at HEAD for such documents
(every 5 minutes, and at once after an intent commit; a document already judged is not read
again). Each is one row: "edge1's committed intent is hand-formatted, so a patch cannot change
it", with the network and the commit read. Its action, **Normalise the formatting…**, opens the
device's Intent tab on Mercury's own formatting, proved formatting only before you commit it
([Normalise the formatting](edit-intent#normalise)). The row clears when the device's intent is
committed in Mercury's own formatting, which every commit since this check is.

**Credentials** (hourly, metadata only, never a value): a credential with an expiry is a
warning 30 days before it expires, a danger row 7 days before, and a danger row as soon as it
has expired. One expiring more than a year out has no row. Where each expiry comes from:

- **NetBox's API token:** NetBox shows it.
- **Proxmox's TLS certificate:** read from the certificate itself.
- **Grafana's and Proxmox's API tokens:** the expiry declared for each on its card (Settings ›
  Default's Grafana card, Settings › Installation's Proxmox card), because neither token can
  read its own. "never" is a valid declaration.

An expiry that could not be read is an **Unknown** row, never a warning: a warning claims a danger
the reader has seen. Each expiry row says where the credential is renewed and where its new
value goes. A device's login credential older than 180 days is a warning naming Rotate; an
SNMP community older than that is a warning whose action is to change it in intent and deploy
it, then set it in the credential store. An
integration that **refuses** the tool's credential (a 401 or 403 to its probe, every minute) is
a danger row of its own, never "down".

**Dashboard settings** (every 5 minutes, with Grafana's dashboards): each network's Fleet and
Device dashboard UIDs are checked against the Grafana that network reads. A UID missing from
that Grafana's list is asked of Grafana directly before anything says it is missing, since the
list may predate an import. If Grafana answers that it holds no such dashboard, the row is a
warning. It names:
- the setting and the UID;
- the layer that sets it ("set in Default's settings, which Branch inherit");
- every network it affects;
- the page that draws nothing until it is fixed;
- where to choose another.

If Grafana could not be asked, the row is **Unknown**. The row leaves as soon as the setting
changes, and the next read checks the new UID.

**AI spend** (read on each recorded AI call and each settings change). There is no standing
spend row; each of these names the amounts it compared, and each has **Open the spend panel**,
which opens the top bar's spend panel in place on the page you are on (see
[What AI is spending](getting-started#ai-spend)):

- **The installation's day cap**, while hosted AI is on and a day cap is set: "AI spend is at
  53% of the day cap ($0.80 of $1.50)", a warning from 50% and critical from 80% (the chip's
  amber and red); and at or over the cap, "AI spend reached the day cap", critical, since every
  AI call is then refused until the day ends. It clears when the day ends (the day cap's
  midnight), or when an admin changes the day cap past today's spend, sets no cap, or turns
  hosted AI off. With AI off or no day cap there is no such row: the chip says "AI off", or
  "no cap".
- **A background feature against its own caps**, per network: at 50% and 80% of its day or
  month cap, and stopped when it reached one. These clear when the day or month ends, or when
  its caps change or it is turned off.
- **A background feature running above its estimate**: at 150% or more of the estimate it was
  approved at ("running at 367% of the estimate it was approved at ($0.4400 a day against
  $0.1200)"), its average over the complete days since it was turned on. It clears when that
  average falls under 150%, when an admin turns it on again with a new estimate, or when it is
  turned off.
- **The provider's workspace usage limit**, while hosted AI is on: "AI is unavailable: the
  provider's workspace usage limit is reached, until 1 November 2026 00:00 UTC; an admin
  raises it in the provider's console", critical. Its cause quotes the provider's refusal
  (which call, when, and the provider's own words) and says every AI call is refused until
  then without asking the provider, people's presses and background features alike. Its
  action: an admin raises the workspace's usage limit in the provider's console, then presses
  **Test** on Settings › Installation › Connections, the AI (hosted) card (its **Open…**),
  which asks the provider again; or wait until the moment. It clears at that moment, or when
  a call is answered (that Test, after the limit was raised), or when hosted AI is turned off.
  When the provider named no moment, it clears 10 minutes after the refusal, when the next
  call asks the provider again.

A feature's rows also carry **Open…** to Settings › AI, where its caps change and it is turned
on again.

## How a row clears {#clearing}

Every row says, under its cause, how it leaves the page: "Clears when …". There are three ways:

- **The condition resolves.** Most rows: the source reads the thing fixed (a later drift check
  finds the device matching, a job's next run reads ok, a device answers again). Doing the
  row's action is how you make that happen; the row leaves at the source's next read.
- **A person acknowledges it.** For an event that cannot un-happen: an unplanned restart, the
  same line authorised again and again, an operation interrupted while it held a device, the
  new host keys a planned window kept, a deploy whose verify could not read back lines the
  device prints in another form; and, within a measured band, a chronic alert and an
  adjacency a device keeps logging down. See below.
- **Time.** An unplanned restart stays for 7 days if nobody acknowledges it; a pending
  approval expires after 48 hours (expiring executes nothing); an adjacency logged down
  clears a day after its last unexplained drop; an AI spend row about a day's or a month's
  spend clears when that day or month ends.

The acknowledgements in force are listed beside the table ("Acknowledged, so not listed"),
each with who, when and why, and those hiding no row now apart ("Acknowledgements in force,
hiding nothing now").

## Acknowledging an event {#acknowledging}

An unplanned restart, or a line authorised again and again, is something that happened, and
nothing will make it resolve. When you have looked into it, press **Acknowledge…** on the row,
say in a few words why it needs nothing more (what you found, or why it was expected), and
press **Acknowledge**. The reason is required (at least three words); it is recorded with your
name, how your identity was established and the time, and the row leaves the page.

- **The answer is drawn on the row at once.** Once it is recorded, the form closes and says
  "Acknowledged.", and the row leaves as the list next redraws. A refusal keeps the form open
  and says why. **Cancel** is offered only before you send: once sent, the acknowledgement
  cannot be taken back by the form.
- **If no answer comes within 6 seconds**, the form says so and frees the button: whether it
  was recorded is not known until the list next redraws. The row leaves if it was recorded,
  and stays with **Acknowledge…** if not.

- **An acknowledgement covers that one event.** A new restart of the same device is a new row;
  the same line authorised once more after you acknowledged it raises the row again. A planned
  window's new host keys, corrected after you acknowledged them (a key moved to the window
  that should have taken it: [Re-key](rekey#planned-window)), are a new row
  too.
- **An acknowledgement covers the device it was made for.** One made for a device that was
  retired or abandoned, or before the Create of the device now holding the name, hides none of
  the new device's rows (an alert series or an adjacency named by the device), and is not
  listed in force. History keeps it.
- **The record keeps the event.** The device's History still shows the restart as unexpected,
  marked "acknowledged" with who and why.
- **A planned window cannot be declared afterwards to clear one.** A restart is planned only
  when the tool did it (its Reload) or was told beforehand (a planned-restart window). A window
  recorded after the tool saw the restart it covers is refused, unless it is marked as a
  correction with its own reason: a restart that really was planned and only recorded late.
  History then says the window was a correction, and why.

### A device restarting as planned {#restarting-as-planned}

A device inside a planned-restart window (its Reload, or a window declared beforehand) is not
something wrong, so it raises no row: *What was checked* says "edge1 is restarting as planned
(until …, by …)" under Reachability, and its Grafana alerts are said there too, held until the
window's end plus a settle margin (19 minutes: its telemetry alerts outlast its return). The
window also sets a Grafana silence on those alerts, as the person who declared it, so Grafana
pages nobody. If the device is still not answering when the window ends, it is a critical row
again, naming the window that ended; an alert still firing after the margin is a row again.

Each alert is judged by its own device, never by what began beside it. Alerts whose onsets fall
within six minutes of each other are grouped into one row ("3 alerts began together"), but an
alert on a device restarting as planned (or drained) is taken out of the group first and said
under *What was checked*, so another device's live alert that began at the same moment is a row
of its own. A silenced alert is never grouped with a live one either: it keeps its level in a
row of its own, saying who silenced it and until when, each silence said once. The row's list
of alerts names, for each, its onset and how that was decided, and on a silenced one "**silenced
in Grafana** by <who> until <when> UTC" with the silence's comment in quotes; a silence Grafana's
list did not return is named by its id, its author and end never guessed. Hover an alert for its
fingerprint and where its device came from, and a silence for its id and what it matches. The
device's own page says the same in its Alerts check, in amber: "held: edge1 is restarting as
planned …".

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
