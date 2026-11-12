# Needs attention

The landing page answers one question: does anything need you?

## What it shows {#what-it-shows}

- **When nothing is wrong**, one line says so, and what was checked is one level down, each
  source with the age of its value.
- **By severity:** a section each for Critical, Warning and Unknown, its count in its heading
  ("Critical · 2"). Critical is always open; Warning and Unknown stay as you last left them in
  this browser. A severity with nothing in it has no section. The line above them counts each
  severity, and when an operation such as a Reload is running, says how many of its expected
  effects are held for it, linked to its card: they are never rows here.
- **One line per item:** its severity, what it is, how long ago it began, and its first action
  (**Open <device>**, or its own page), which works without opening the item. While a run holds
  the device an item's action would change, the action is not offered: a second line under
  the item's title reads "<run> running since <time>, by <who>", and the right side of the
  line holds **Open the run** alone, which opens the device's page on that run's card; the
  action returns by itself when the run ends. Press the line to
  open it: **What to do** comes first (every action with its How does this work?, how it
  clears, and **Acknowledge…** for an event), then why: for an item a Grafana alert raised,
  **Explain**, the same answer Monitoring › Alerts keeps for that alert's evidence (opening the
  item asks the model nothing; with no answer kept, Explain is offered behind its cost); for
  anything Mercury found itself, **Why this happened**, written by Mercury from its own record
  with no AI. A self-healing can't-fix carries one closed line there too, **The steps Mercury
  took: stopped at <step> · N steps · Show**; opened, it draws the one stepper: each step
  Mercury took, done, failed or not reached, the step it stopped at named, and **The steps
  taken**, one line a step ([Self-healing](heal#act)). A lost telemetry stream's card carries
  its last run the same way, **The last run, <how long ago>: <how it ended> · N steps ·
  Show**. Then the **Details**: the alerts, the devices with their networks, since when and
  which source, and last **Details for the record**, closed until you open it: the record's
  ids, hashes and steps, its times in UTC. A time a self-healing item names (when a change was
  made, when a symptom began) is drawn in your browser's time zone, with UTC on hover.
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
- **On a laptop kit, the server's own checks are marked, not raised.** An
  installation set up by the final SDN lab's laptop kit (`installation_kind` is `laptop_kit`,
  written by the kit's `init`) has none of the Mercury host's install, so those checks are not
  rows. Each is one line of its own under *What was checked*, naming its source and the check,
  saying
  **not applicable on a laptop kit** and why. They are:
  - the server's systemd jobs: the NetBox backup and its restore test, the heartbeat,
    telemetry and startup checks;
  - the Update button's updater, and the nightly VM images while Proxmox is not configured;
  - the monitoring settings left empty: the SNMP exporter's config, the syslog host and the
    YANG push script;
  - the readers and sources that compare the running commit with GitHub: origin, CI, the two
    CI runners and the scheduled workflows;
  - the Grafana and coverage readers, and Grafana's alerts, while Grafana (or Prometheus and
    Loki) is not configured;
  - the host steps a release owes the Mercury host.

  Everything else is raised as on any installation: NetBox not answering while the kit runs, a
  device unreachable, anything about the kit's own network's devices. A kit that configures
  Grafana or Proxmox gets their rows back. On the Mercury host, the default, nothing is marked.
- **A network with no devices yet marks its device checks.** On any installation, while a
  network holds no device, its drift check, its baseline and its intent formatting are each one
  line under *What was checked*, saying **no devices yet** and why, never a row. Its first
  device makes them rows again, exactly as before. A network whose device list cannot be read
  is not "no devices": its checks stay rows.
- **A check waiting for NetBox to start is a line, not a row, until its grace ends.** When a
  read of NetBox finds nothing answering at all (the connection refused, reset, or timed out
  before any answer), Mercury asks again after 15 seconds, doubling to 5 minutes, until NetBox
  answers. For two minutes from NetBox's start (Mercury cannot read NetBox's own start, so from
  Mercury's), the check is one line under *What was checked*: **waiting for NetBox to answer
  (since …, grace until …)**, marked like a source that could not be read and never drawn as
  fine. Two minutes is about 2.5 times NetBox's measured start, 46.5 seconds from its
  containers' start to its first answer. Past the grace it is the row it always was, and that
  row clears at the next answered read. An HTTP error, a certificate refused or a wrong answer
  is NetBox answering, and is a row at once. The checks it covers: NetBox's stored
  credentials, NetBox against the committed goldens, and the NetBox API token's expiry.
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

A live update keeps what you were doing. Only the rows that changed are redrawn; every other
row is left exactly as you have it, so the page stays where you scrolled it, the rows you
opened stay open, the control you were on keeps the focus, and nothing flashes. A row whose
Acknowledge… form you have open, or whose proposal you are reviewing, stays as it is while the
rest of the list updates around it, and says newer data is waiting. New rows that would arrive
above where you are reading are not drawn there, since that would push the page down: a button
at the top of the window says how many, **N new, show them**, and pressing it draws them and
takes you to them. This is the same on every page that updates live.

The other rows, each with its own cause and action: deploys that failed or were verified and
not saved to startup; a deploy that landed and whose verify did not pass, its save to startup
held for a person (a warning naming verify's own words; **Persist <device>…** saves it, and no
control rolls back a change whose verify did not fail yet, so the row says that until it is
saved startup holds the device as it was before the change); a deploy, recorded before saves
were held, that landed and was saved while verify could not read back some
of the lines it sent, a warning naming the lines (read them in the device's golden on its
History tab: acknowledge the row with that reason when the device prints them in another
form, or plan the deploy again when they are absent; a later deploy that misses a line raises
it again); operations interrupted while they held a device (the process ended
mid-run); a device's SSH host key that changed (**Re-key…** on its page), and the new keys a
planned window kept; the records database's stores that do not match or do not answer; the
scheduled rotation's timer, stopped on a failure; templates behind the shipped version in a
way that drops lines; the log redaction found unhealthy; the CI verdict on the running commit,
and a pushed release whose CI failed; a scheduled quality job (each workflow with a schedule,
such as the weekly mutation run) whose newest scheduled run failed, or that has not succeeded
within its period and GitHub's start delay, with a link to the run (it clears only when a
scheduled run succeeds; a dispatched one does not clear it); the verdicts on one commit
(GitHub's CI against the commit gate's recorded verdict, and the local runner's where this host
has one): a red from GitHub on the commit this host runs, after it was deployed on the gate's
or the local runner's green (a warning, since the release keeps running, naming where it
failed: stop new work, rerun GitHub's run once, and if it stays red fix forward or roll back
with the `scripts/nmas-rollback` command it names; one notice of the kind "CI disagrees with
the deployed release" goes to the teams your networks tell), a commit they disagree on, or a gate note or local record that cannot be
trusted or read; host steps owed; a NetBox-sourced network's unreadable
inventory; a rollback's record; pending onboardings (overdue, or still holding a staged
credential); Grafana's rule groups that stopped evaluating, and rules that read no data; the
fleet's heartbeat stopping at once (one row, not one per device); the routing adjacencies
Prometheus reads (a link down, adjacencies it cannot measure, or its read failing); and drift
(a drifted, skipped or unreachable device, a check that is off, failed, never ran or is
old); and SDN (an SDN loop a restart stopped; one row per incident awaiting a person, red
once it has gone unanswered past its network's escalation threshold, 15 minutes unless set,
and saying no on-call integration exists to notify; a response's flows missing before their
hard timeout; a link down whose reroute is not verified, red once a verify found it not
rerouted, opening its card on SDN › Responses ([Link failures](sdn#link-failure)); and a
network whose SDN controller is not answering; see [SDN](sdn#controllers)). Each network's own Prometheus has its own row comparing what it scrapes with its
networks' inventories ("…, for <network>'s Prometheus"; see [Settings](settings#network)),
and each network's own Grafana its own alerts and token expiry.

**Adjacencies logged down.** Prometheus reads each device's routing tables once a minute, so
an adjacency that drops and comes back between two reads never shows there. The device's own
log does show it. Mercury reads the routing adjacency changes every managed device logged
(`%OSPF-5-ADJCHG`, `%OSPFv3-5-ADJCHG`, `%BGP-5-ADJCHANGE`) and raises one row per adjacency.
The row names the logging device, the protocol, the neighbour (by its device where committed
intent gives its router id or address, the id beside it), how many times it went down in the
last day, the last time and the reason the device gave.
- A drop inside a planned restart's window, of the logging device or of the neighbour, or
  around a deploy to that device, is counted under What was checked and never raised.
- An adjacency that flaps for a known reason can be acknowledged within its band: the highest
  daily count of the last week. It stays quiet while the day's count stays at or under that,
  and returns, saying so, when it goes above.
- An acknowledgement covers the drops up to its own time, and the down/up cycle under way then
  until it settles (15 minutes with no drop). Any drop after that brings the row back, naming
  who acknowledged it and when, and the drop's time, even inside the band.
- For a planned quiet period, choose its length in the form's second choice, "A planned quiet
  period", 1 to 24 hours.
  Every drop to its expiry is covered, inside the band or not. The acknowledged list shows the
  expiry, and a drop after it brings the row back.
- With no drop for a day, the row clears.
- With no Loki configured there is no log to read. What was checked says so once, "no Loki
  configured", with what a Loki would show, and nothing about it is a row: not the source, and
  not its reader under job health. A Loki that is configured and stops answering is still a
  row, as critical as before.

**A duplicate router-id.** Two routers given one OSPF router-id overwrite each other's routes:
adjacencies flap and what is behind them becomes unreachable, and only the devices' own log
says why (`%OSPF-4-DUP_RTRID_NBR`, its area and AS variants, and OSPFv3's). The same reader
asks for those lines over the last hour and raises one critical row per duplicated id: "edge1
and edge2 both claim OSPF router-id …" when both routers logged it (each sees the other's
hello carrying its own id), or the one device that logged it, beside the neighbour address it
saw (by its device where committed intent gives the address). The row names each interface,
and which router departed from its committed intent where intent gives the id to one of them;
its action opens that router's Intent tab. A planned restart never explains it. The device
repeats the line about every 66 seconds while the duplicate holds, so the row clears once no
line has come for 165 seconds, at the reader's next read. Self-healing reads the same lines
again after a router-id fix: "no duplicate router-id logged" is the fix's check.

Oxidized is retired (2026-10-08), and its freshness check with it: nothing here compares
Oxidized's copy. A change made on a device outside Mercury is raised by the drift check, which reads each
device's running configuration against its golden on the interval set for it (four hours
unless changed). A drifted device's row carries both answers: **Capture** records what the device
holds as its golden (the change was wanted), and **Deploy intent** puts its committed intent back
(it was not); each opens its card on the device's page, with its preview and confirm.

**When the change came from outside Mercury and something broke at the same time, the row
never offers Capture.** Capturing then would record the fault as the device's approved state,
and self-healing would later put the fault back. Mercury knows both from self-healing's
incident for the device: its configuration-change line, judged not Mercury's (or no record of
Mercury making it), and a symptom with it (an alert, an adjacency down, a logged drop) on the
device or on a device inside its blast radius. The row then says so in its title ("edge1 was
changed from outside Mercury, and something broke at the same time") and in its words (who
changed it, when, and what broke), and offers two actions: **Put it back to intent…** (the
device's Deploy: committed intent, merge-only, each line intent lacks removable with a reason)
and **Keep it: add it to intent…** (the device's Intent tab, its editor open, committed with
your reason). The queued drift item's Capture does not replace them. Today a deploy is planned
against the device's golden, which a drifted device has left, so Put it back's apply refuses
with nothing sent; the row says so, and Mercury cannot yet put a drifted device back to intent
without capturing it first. When self-healing's incidents cannot be read, whether something
broke is not known, and Capture is not offered until they can be. Capture stays offered where
the change broke nothing, and where self-healing holds no incident for the change (it is off,
or saw no change): the words say which.

**Persist <device>…** is the action of three rows: a deploy that was verified and not saved to
startup, a deploy whose save was held because its verify did not pass, and job health's row for a device whose running configuration holds the only working
credential. It opens the device's Persist card on its page, with its preview and confirm (see
[Persist](persist)); the row clears once a save's read-back matches. A device's "not monitored"
row offers **Preview the apply…** when the network's monitoring profile already covers what is
missing, and **Propose on Profile…** when it does not (the network has no profile, or no
section of it applies to the device): it opens the Profile tab of Monitoring with Propose's
card open ([Profile](monitoring#profile)), and the profile, once proposed and committed, is
applied from there.

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

**AI spend** (read on each recorded AI call and each settings change). One row stands while a
condition lasts (no cap); the others name the amounts they compared. Each has **Open the spend
panel**, which opens the top bar's spend panel in place on the page you are on (see
[What AI is spending](getting-started#ai-spend)):

- **AI spend uncapped**, while hosted AI is on and the installation's day cap is unset (an
  admin chose **No cap** on the AI (hosted) card), a warning: "AI spend uncapped: the
  installation's day cap is unset". Its cause names who unset it, when and the reason they
  gave (or that the settings record cannot say), and that Mercury then refuses no AI call for
  the day's spend, so the provider's own limit is the only backstop. Its action: an admin sets
  a day cap on Settings › Installation › AI, the AI (hosted) card (its **Open…**). It clears
  only when a cap is set. With hosted AI off it is not drawn, since no call is made; it
  returns when AI is on again. The day cap is the only AI cap that can be unset: a background
  feature's day and month caps are always amounts.

- **The installation's day cap**, while hosted AI is on and a day cap is set: "AI spend is at
  53% of the day cap ($0.80 of $1.50)", a warning from 50% and critical from 80% (the chip's
  amber and red); and at or over the cap, "AI spend reached the day cap", critical, since every
  AI call is then refused until the day ends. It clears when the day ends (the day cap's
  midnight), or when an admin changes the day cap past today's spend, sets no cap, or turns
  hosted AI off. With AI off or no day cap there is no such row: the chip says "AI off", or
  "no cap" (and with no cap the row above stands).
- **A background feature against its own caps**, per network: at 50% and 80% of its day or
  month cap, and stopped when it reached one. These clear when the day or month ends, or when
  its caps change or it is turned off.
- **A background feature running above its estimate**: at 150% or more of the estimate it was
  approved at ("running at 367% of the estimate it was approved at ($0.4400 a day against
  $0.1200)"), its average over the complete days since it was turned on. It clears when that
  average falls under 150%, when an admin turns it on again with a new estimate, or when it is
  turned off.
- **A background feature's approval ending**, per network: from 3 days before its 14-day
  approval ends, "The approval of <feature> on <network> ends in 2 days", a warning naming who
  turned it on, when, and the moment it ends; once it has ended, "The approval of <feature> on
  <network> ended <time>", critical, since the gateway then refuses its calls. Its action: turn
  it on again in Settings › AI (**Turn on again…** on its row, accepting its current estimate
  for another 14 days), or turn it off. It clears only then, never by time, so an ended
  approval is never silent.
- **The provider's workspace usage limit**, while hosted AI is on: "AI is unavailable: the
  provider's workspace usage limit is reached, until 1 November 2026 00:00 UTC; an admin
  raises it in the provider's console", critical. Its cause quotes the provider's refusal
  (which call, when, and the provider's own words) and says every AI call is refused until
  then without asking the provider, people's presses and background features alike. Its
  action: an admin raises the workspace's usage limit in the provider's console, then presses
  **Test** on Settings › Installation › AI, the AI (hosted) card (its **Open…**),
  which asks the provider again; or wait until the moment. It clears at that moment, or when
  a call is answered (that Test, after the limit was raised), or when hosted AI is turned off.
  When the provider named no moment, it clears 10 minutes after the refusal, when the next
  call asks the provider again.

A feature's rows also carry **Open…** to Settings › AI, where its caps change and it is turned
on again.

**Lines withheld from AI requests** (read on each recorded AI call). Before any AI request
leaves, {{product}} withholds each line of the data it carries that reads as an instruction to
the model ([Lines withheld as instructions](alert-evidence#withheld)). One warning row per AI
feature that withheld a line in the last day: "2 lines aimed at the model were withheld from 1
explain call in the last day", its cause naming the kinds of words found, the newest call,
what it was about and where in its data each line was. Someone who can write a device's logs,
descriptions or records may have aimed them at the model. Its action: read the call's record in
History and the lines where they were read, and find who wrote them. It clears a day after the
last such call, or when you acknowledge it with a reason and what it was: a true positive
(someone aimed the lines at the model: investigate who wrote them), benign or a test, or a false
positive (the words were not instructions; these are the flagger's tuning evidence). What you
chose is recorded with the acknowledgement and shown in History. A later call that withholds a
line raises it again. An evaluation's own calls (a recorded case planting a line on purpose)
raise no row.

## How a row clears {#clearing}

Every row says, under its cause, how it leaves the page: "Clears when …". There are three ways:

- **The condition resolves.** Most rows: the source reads the thing fixed (a later drift check
  finds the device matching, a job's next run reads ok, a device answers again). Doing the
  row's action is how you make that happen; the row leaves at the source's next read. A
  self-healing proposal (a Critical row: "<device>: <what changed>. Mercury has a fix …: it
  needs your decision") leaves once a person decides on its card: **Review the fix…** opens the
  row to it, with **Approve and run on <device>** (by the proposal's hash, a reason optional
  unless a line needs one) and **Decline** (with a reason; nothing is sent)
  ([Approve or decline a self-healing proposal](heal-proposal)). A dry-run record leaves once
  you mark it on its row: **Was that right?** opens it to **Right** and **Wrong…**
  ([Dry run: Right or Wrong](heal#mark)). One change is one row: where self-healing holds a
  device's change as a proposal, a can't-fix or a hold, that device's drift ("<device> has
  drifted from its golden") is drawn inside that row as "Also: …", never as a Critical row of
  its own; a dry-run record goes the other way, inside the drift row, which is then the row
  to act on.
- **A person acknowledges it.** For an event that cannot un-happen: an unplanned restart, the
  same line authorised again and again, an operation interrupted while it held a device, the
  new host keys a planned window kept, a deploy whose verify could not read back lines the
  device prints in another form; within a measured band, a chronic alert and an adjacency a
  device keeps logging down; and, until the workflow's next scheduled run, a scheduled
  quality job's failed run. See below. A host step a release owes is closed on the Update
  page instead: its row's one action, **Open the Update page**, is where you say it is done
  or decline it with a reason ([Declining a host step](update#declining-a-host-step)).
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

### A scheduled job's failed run, until its next scheduled run {#acknowledging-a-scheduled-job}

A scheduled quality job (the weekly mutation run, the coverage nightly) whose newest scheduled
run failed is a row until a scheduled run succeeds; a dispatched run does not clear it. While
the fix waits, you can acknowledge it with a reason, and the acknowledgement **expires** at the
workflow's next scheduled run, read from its cron in UTC ("0 14 * * 0": the next Sunday at
14:00 UTC).

- **When you acknowledge it**, the tool reads the workflow's cron and records the moment of its
  next scheduled run with your reason. If the cron cannot be read, nothing is acknowledged and
  the form says why.
- **Until then** the row is not listed, and the acknowledged list says "Acknowledged by <you>
  until the next scheduled run (<when>): <reason>". The count re-reads at that moment.
- **At that moment** the row comes back by itself while the job is still red, naming the
  acknowledgement that ended, so a failure that persists is never hidden for longer than one
  period. GitHub starts a scheduled run hours late at times; the row comes back at the cron's
  time all the same, and leaves when a scheduled run succeeds.
- **A later failed run is a new row**: the acknowledgement covers the run it was made for, by
  that run's id.
- Only a failed run is acknowledged this way. An overdue job (no success within its period)
  and a job whose runs cannot be read clear only when the condition resolves.

### A device restarting as planned {#restarting-as-planned}

A device inside a planned-restart window (its Reload, or a window declared beforehand) is not
something wrong, so it raises no row: *What was checked* says "edge1 is restarting as planned
(until …, by …)" under Reachability, and its Grafana alerts are said there too, held until the
window's end plus a settle margin (19 minutes: its telemetry alerts outlast its return). The
window also sets a Grafana silence on those alerts, as the person who declared it, so Grafana
pages nobody. If the device is still not answering when the window ends, it is a critical row
again, naming the window that ended; an alert still firing after the margin is a row again.

What the operation predictably causes elsewhere is held the same way, until the same time: the
devices its preview said Mercury loses reach to ("access1 is out of Mercury's reach as
expected while edge1 restarts as planned (by …); expected back by …"), an adjacency with the restarting
device at one end, its protocols that cannot be measured while it is down, a neighbour's logged
drop to it, and a drift check that could not read either device (the next run reads them
again). Each is said under *What was checked*. A device the preview did not predict is raised
as usual. Only a Reload records what it predicts today; a window declared by hand holds its own
devices alone.

Each alert is judged by its own device, never by what began beside it. Alerts whose onsets fall
within six minutes of each other are grouped into one row, its title naming where and what
("edge1: 2 telemetry streams lost (101, 102)", or "2 devices (edge1, edge2): 2 alerts: Device
unreachable (SNMP)"), but an
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

A device's lost telemetry streams are always a row of their own, whatever began beside them.
The row carries **Re-subscribe
<device>'s telemetry (<ids>)…**, which opens the row to its card: what will be true afterwards,
each subscription ticked, the exact program, a reason and the button
([Re-subscribe a lost telemetry stream](telemetry-resubscribe)). A device that two networks
name is not offered it, and the row says so.

### How critical an alert's row is {#alert-severity}

An alert's row takes its level from its rule's own `severity` label in Grafana: `critical` is
Critical, `warning` is Warning, and an alert whose rule is labelled `info` is a record, said
under *What was checked* and never a row. A rule with no severity label is Critical, as every
alert was before the label was read, so a new rule never arrives quieter; a label with any
other value is Critical too, and the row's **Details for the record** name the value. A row
of several alerts takes the worst of them. The level is the rule's: to change it, change the
label on the rule.

Mercury's own lost-stream rules are labelled `warning`: a lost stream is visibility lost
while the device still answers. Critical is an outage, something down or unreachable for its
users, so a lost stream is Critical in one case only: **its device is not answering.**
Whether it answers is Mercury's reachability reading (a probe of each device every 5 seconds,
taken as current for 150 seconds). A device counted as not answering has its lost streams
drawn inside its not-answering row, as "Also: …", never as a second row.

**Several devices that lost their streams together** are one row, not a row each: lost streams
on three or more devices that began within 150 seconds of each other (or on every streaming
device, when there are two) are one Warning, "3 devices stopped streaming telemetry together
(edge1, edge2, edge3)". What they share is the collector, the path to it, its scrape, or one
change made to all of them; a collector losing every stream is a monitoring gap, not an
outage. Each device's own row is under it, closed, still offering its Re-subscribe. A device
not answering is not counted: it is on its not-answering row.

When the reachability reading cannot say whether the device answers (it could not be read,
it is older than 150 seconds, or it holds no device of that name), the row stays a Warning
and its title says so: "edge1: 2 telemetry streams lost (101, 102) (not known whether edge1
answers)".

### A lost telemetry stream, opened {#a-lost-telemetry-stream}

Opened, a lost telemetry stream's row says six things first, above What to do. Each is written
by Mercury's code from its own records, with no AI:

- **How long, and what it costs:** "edge1 has sent no telemetry to the collector for 37 hours.
  Monitoring for edge1 is blind until it does." The time is measured from the alert's own
  onset to the reading the row stands on, never from the device's uptime. It says "no
  telemetry" only when every lost-stream rule Grafana holds for the device is firing;
  otherwise it names the subscriptions that sent nothing. When the reading of Grafana's alerts
  is older than its promise, the sentence says so and speaks of then, not now.
- **Whether the device answers:** "edge1 answers Mercury's reachability probe (ICMP, then TCP
  22): it is reachable, and its telemetry is not arriving." This is why the row is a Warning
  ([How critical an alert's row is](#alert-severity)). A device that missed its last probes
  and is not yet counted as not answering is said with its count, in amber; a reading that
  cannot say is "Not known whether edge1 answers: …", naming why, in amber.
- **What Mercury cannot see until it is back:** one line naming edge1's telemetry-only panels
  on its Monitoring tab, its Telemetry column on Monitoring › Coverage and its Telemetry
  rates in History. Self-healing reads the stream only to say it is back (Re-subscribe's
  Verify and the diagnosis); nothing else it checks reads it.
- **Seen before on edge1 (when):** drawn only when a past loss on the same device matches:
  when it began and cleared, how it ended, and how long that held before telemetry was lost
  again, with **Open that incident** (Monitoring › Alerts › History, for that device). The
  match is the same device, the same symptom and the same cause first, then the nearest in
  time. How it ended is only what a record shows:
  - **a Mercury operation**, with **Open that operation's record**: a re-subscribe whose own
    check read the stream back is said to have fixed it; any other operation that ran during
    it is said as that, and that no record says it cleared the loss;
  - **no Mercury operation recorded**, with a configuration change in the device's log during
    it, its time, and whether it was made on the console or which account and address the
    line names. It is never called a fix by hand: the log shows a change, not what it did;
  - **it cleared by itself**, said only when the device's log holds other lines from that
    time and none is a configuration change. A log that holds nothing from then, or cannot be
    asked, cannot say nothing changed, and the line says which.

  A store that could not be read (the alert history, the operations' record, the receipts) is
  named in the line with why; it is never read as "never seen".
- **Does it need you?** "Yes: the fix changes edge1's configuration, so a person approves it.
  If you don't, edge1's telemetry stays lost."
- **Mercury's diagnosis:** the newest "a telemetry stream lost" diagnosis recorded since this
  loss began ([A telemetry stream lost](diagnose#stream)), in plain words, with when it was
  read and what it says to do next: "a session that carries nothing (half-open). edge1 reads
  Connected on connection 496, the collector holds edge1's session, and no data has arrived
  on it for 37 hours." Otherwise it says which of three things is true: none is recorded for
  this loss (one read before it began is never drawn as this loss's), one was asked for and
  not made, with its reason, or the record could not be read. Self-healing runs that
  diagnosis by itself where it is on for the device's network; no control on the row runs it
  yet.

The action follows: Re-subscribe, in What to do. What matched, what was searched and how each
sentence was measured are under **Details for the record**. Mercury searches its records when
it reads Grafana's alerts (once a minute, and only while a stream is lost), never when the
page is drawn, so a diagnosis recorded just now appears with the next read.

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
- **When the alert stops firing and fires again after the acknowledgement,** the row comes
  back, naming who acknowledged it and when this firing began. An acknowledgement covers the
  firing under way when it was given, never a later one, unless it named a planned quiet period
  (1 to 24 hours) that has not yet ended.
- Only an alert on one series, whose rule is a Prometheus query ending in a threshold, can be
  acknowledged this way. Any other alert clears when it stops firing.
