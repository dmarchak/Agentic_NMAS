# History

What happened to the network and its devices, and when, in three tabs: **Timeline**, one
timeline of everything the tool records; **Query**, questions asked of the network's history;
and **Baselines**, the network's baselines. The remote's state is at the top.

## The remote {#remote}

One sentence says whether everything is committed and whether it is pushed to the network's
remote repository, with when that was last checked. It names up to five paths that are not
committed, and how many more, and lists each with what it is and what clears it: a golden no
save committed (Capture as golden on the device's page records it through the save path),
intent not committed (save it from the device's Intent tab), a template not committed (save it
again from Templates' Edit…), Mercury's own record (committed with the network's next commit),
or a file nothing in Mercury writes (changed outside Mercury on the host). A network whose folder has no repository yet (one made before
networks were created with theirs) says "No repository yet: the network's first commit makes
it": its first save, seed or other commit through the tool makes the repository. Any other
failure to read the folder says "The working tree could not be read", with git's own error.
**Verify the remote** runs the read-only
checks against it (the key's scope first, and only if the key is scoped to one repository a
read, that it is private and the right repository).
**Push now** appears while something is not pushed; it needs a person, and the sentence
redraws once the remote is read again. **Set up the remote…** (or **Remote set-up…** once one
is configured) opens the network's remote card in place ([Publish to a remote](publish-remote)).

Under it, from the network's own record, so they stay whatever redraws the card:
- the last failed push: when, who and why. A successful push clears it.
- the last Verify: when, who, and whether every check passed or which failed, each failed
  check with **To fix:** and what to do.

When that record cannot be read, the card says so ("The list's remote record cannot be read"),
naming why.

## Timeline {#timeline}

Every record the tool keeps, across every device, newest first, for the time you choose (7 days
by default). It also holds the records that belong to no one device: a commit to the monitoring
profile or the templates, a Save All's baseline decision, an update of the app, and each
[import into NetBox, Remove from NetBox and Stop tracking](netbox-import) of this network (kind
**NetBox**: who confirmed it, when it started and ended, and its counts in the NetBox page's
own words; an import of every network is on each network's timeline it names). A device's
History tab is this same timeline filtered to that device, read by the same code, so the two
can never show different things.

Each record is one line:

- **When.**
- **Kind.**
- **Device:** one device, a few, how many, "every device" (a window for the whole list), or
  **fleet** for a record about no one device.
- **What.**
- **Who.**

Open a line for the full record underneath. It shows:

- the reason and each step with its result;
- how the person was identified;
- for a commit, **Show the change**: its diff, with every secret masked;
- for an AI call, what it was about (the alert, the question's network, or the installation),
  the model, the tokens in and out, the cache's write and read, the cost, and what became of
  the answer (filled the builder, shown, asked a question back, or refused by validation, with
  why). **Show the prompt and the answer** draws two windows:
  - **Sent to the model:** the instructions, then each context block and each data block by
    its name, exactly as they left the host, with the model, the most tokens out, the
    thinking and the answer's schema. A large part is folded, its size said.
  - **Received:** the answer, laid out for reading.

  Secrets show only as their masks: the prompt was masked before it left the host, and the
  unmasked form is never stored. A call refused before it was sent says so. **Open what it
  produced** opens what the answer made: Explain's answer in its alert's evidence pack, or the
  builder as Ask in words filled it (every choice in its address);
- **Open (device)'s History** for each device the record names. A device's own History tab
  shows the AI calls about that device.

The Baselines tab works the same way, with each baseline's reasons under its line.

Filters:

- **Device:** that device's records only; the fleet's own records drop out. When the name
  belonged to a device that was retired and a new device has been onboarded under it, the
  records start at the retirement: its row says the earlier records are the retired device's,
  and History of every device still holds them. A device's History tab reads the same way.
- **Person.**
- **Kind,** in four groups:
  - **The repository:** goldens, intent, commits (golden, intent and profile together) and
    measured-unchanged saves.
  - **What ran on a device:** deploys and restores, rotations, persists, privileged commands
    (Tier 2), reloads, onboarding and adopt, runs cut off midway, and authorised retries.
  - **What happened to a device:** restarts and planned windows.
  - **Decisions and records:** approvals, acknowledgements, break-glass exports, credential
    profiles, expected islands, Topology layouts, saved views, reveals, SSH host keys,
    baseline decisions, app updates, NetBox imports and removals, Grafana writes (each
    silence Mercury set, moved or expired in Grafana, for whom, with Grafana's answer; one
    Grafana refused is drawn in red; and each re-measure of the heartbeat windows, written from
    the heartbeat check's row on Needs attention, who wrote it and each of the network's
    devices' windows), and Show commands runs.
- **Since.**
- **Jump to:** a day; the timeline starts at its end (below).

A row's **who** is a verified person's email, or, for a host command, the host login labelled
"host login, not a verified identity". A deploy of part of intent is named by what it sent:
**Monitoring profile applied**, **IP SLA probes sent** or **Monitoring templates deployed**,
never "Deployed". A withdrawn approval names what withdrew it and why.

**Every kind** and **Commits only** are one click away in the Kind menu. Under the filters, the
kinds most often looked for are one click away too: **All**, **Goldens**, **Intent**, **Deploys
and restores**, **Measured, unchanged** and **Restarts**, each keeping your device, person and
time filters. A kind is chosen before the list is cut to its newest records, so a device's last
golden is found under **Goldens** however many saves came after it. A kind the tool does not
know (a mistyped link) is not applied, and the list says so above its rows ("Not applied: the
kind filter 'goldn' is not a kind History records") and draws every kind; a device or person
that is not a name is said the same way. Each filter is part of the page's
address, so a view is a link you can share. A record store that could not be read is said
above the list.

**Load more and Jump to.** The timeline shows 50 records at a time, newest first, and says how
many it read ("Showing the newest 50 of 316 read"). **Load more**, under the last record, reads
the next 50 older than it and draws them in place under it; it shows "Loading…" until they
arrive. It asks for the records older than the last one shown, by its time and its id, never
by a page number, so records that arrive while you read do not shift what comes next. Every
filter applies to the records it reads, and the page's address takes the place it reached
(`before=<time>~<id>`): Back returns to the place before, and a link you share opens at the
same place, with **Back to the newest** above the records. **Jump to**, beside Since, starts
the timeline at the end of a chosen day (UTC; `on=YYYY-MM-DD`), with every other filter;
Load more then reads back from there. When nothing older is left, the list says "No older
record than these." Most records are read from the place itself, so any depth costs the same.
A few stores can only give their newest records (deploy and restore receipts, app updates,
Show commands runs, Tier 2 runs and console runs): Mercury reads more of them when a page
needs it, up to 3,200 records a store, and a page further back than that says, under the
records, which store it could not reach ("Load more does not reach further back in …"), never
drawing it as nothing having happened.

**One AI call.** Explain's answer ("This call in History") and Ask in words' filled notice
("this call in History") link to the call's own row, `?call=<id>`: that one call, opened,
however old, with **Every AI call** and **Every record** beside it.

**From an AI call to the device, both ways.** A change drafted in words and committed (Change
it in words) is an intent change whose row links **Open the AI call that drafted it**; the
call's row says it was committed. A deploy's row names the intent it deployed and links **Open
the intent change it deployed**, and an intent change's row links **Open its deploys**. Both
open `?commit=<sha>`: that commit's row and every deploy that sent it, among the newest rows
of each record, said as such. A deploy recorded before Mercury recorded this says "not
recorded", and a restore says it sent a golden, not intent.

A network with no repository yet says so once above the list ("No repository yet: the network's
first commit makes it"), naming the records the repository will hold (the golden and intent
histories, the measured saves, the other commits, the baseline decisions), never "could not be
read"; a repository git cannot read keeps each of those as could not be read, with git's own
error. A commit whose record is known to be wrong says so in its row.

**Only this network's records.** Some records are kept once for every network and name a device
but no network: rotations and persists, acknowledgements, older reveals and planned windows
declared with no network. The timeline draws one of those only when its device is one of this
network's, so a network with no devices draws none of them, never another network's. When the
network's inventory cannot be read, the page says so above the list and draws none of them,
since which are this network's cannot be told.

**Who changed it, and can it be trusted.** Under the filters, one line counts the commits in the
window the filters draw by how their person was identified: signed in through the access proxy
(verified), a host login, not verified, or made before the tool recorded how. For example,
"41 of 52 commits in this window carry a verified identity", with a badge for each other kind.
When a filter narrows the window, the line says which ("shown (person: alex)"). A window with no
commit says so rather than "0 of 0". **Show only these** keeps your filters and lists just the
commits not verified; **Show every identity** undoes it. Each commit's own row says how its
person was identified when it was not a verified sign-in.

## Reveal a version {#reveal}

A golden row (on a device's History tab, or on History when the commit is one device's) offers
**Reveal <device>'s version…**: the device's golden at that commit, unmasked, drawn under the
row. **Show the change** is masked, like every screen; a reveal is the one place secrets are
drawn in the clear. It needs a verified person, and it is recorded in the reveal record (who,
when, which device and which commit) before the text is drawn; a refusal draws nothing, and so
does a reveal the record could not take: nothing is ever shown unrecorded.

## Reveals on the Timeline {#reveals}

Every reveal the reveal record holds is one row on the Timeline under **Reveals** (in Decisions
and records), and on the device's History tab: a golden version, a golden diff, a pending
device's bootstrap config (to a person, or served to the device over TFTP), and a log line.
Each says who, when and which object (the device and the commit, the line's stream and time),
and the reason where the reveal asked for one (a log line's); how the person was identified is
under the row. **The value is never drawn**: the record holds what was looked at, never what was
seen. A reveal recorded before reveals named their network is drawn by its device's name, and
says so. The break-glass export is its own row, under Break-glass exports. The Timeline redraws
when a log line or a bootstrap config is revealed; a golden version, revealed in place inside
the Timeline, is listed the next time it is drawn, so the redraw does not take away the version
you are reading.

## Query {#query}

Ask the network's history, starting from a question. The tab says first **what the history
holds**: how many days of metrics are kept at full detail and whether a long-term store answers
past them (both from this network's settings), and how long logs are kept and when the log
store began (the logs reader's own count). Then the **ready-made questions**, each opening its
answer: **Syslog by device** opens the network's syslog by device (see [Logs](logs));
**Interface errors and discards over time** opens a chart of discards per second, for every
device or, choosing one, by its interfaces, over 24 hours to a year. It is asked of the
network's Grafana the way a Monitoring panel is, from the store that keeps the range: a range
past the days the live store keeps is refused, naming the setting, unless a long-term store is
set. Its own query is shown under the chart; the device, the interface and the range are in
the address, so Copy the link carries the question. Hover the chart to read it, as in
Grafana: the time under the pointer, then each series with a value there, largest first, in
the chart's unit (every Monitoring panel's chart reads out the same way). **CPU and memory trend** is asked the same
way, per device: each device's CPU (its 5-minute busy) and its memory (the Processor pool's
used share) as two lines on one percent axis; memory is drawn only where the device's scrape
carries a memory pool, and the page says so under the chart. **Routing neighbour changes**
draws each device's established neighbours over time, per protocol (OSPF and OSPFv3
neighbours in state full, BGP peers established): a dip is a neighbour going down, its return
the neighbour coming back, and a neighbour down and back between two reads (60 s) is not seen.
Needs attention lists such a drop all the same when the device logged it going down outside any
planned restart or deploy: one row per adjacency, clearing a day after its last drop, or
acknowledged while its daily count stays within its measured band.
**Restarts** draws each fall of a device's uptime counter in the step it fell in, and under the
chart **Mercury's restart record** for the range: each restart, planned or not (judged against
the planned windows recorded), its window and the device's own reason, and the day the record
began. A fall the chart shows with no row in the record is one Mercury did not record.
**Telemetry rates** draws the telemetry series each device's stream holds (IOS-XE model-driven
telemetry), by YANG model for one device: a device that stops streaming falls to nothing.

**Your own query.** Under each metrics answer, **The query (PromQL), editable** holds the
question's own query: change it and press **Run**, and the chart draws yours, from the same
store and over the same range. The title is marked **edited**, the question's own query is
shown beside yours, and **Back to the question's own query** returns to it. Your query is in
the address, so Copy the link carries it. **Ask your own (PromQL or LogQL)…**, under the
questions, opens the metrics builder ([below](#ask-metrics)); **Code** on its Mode switch is
this page with no question, where you choose the language, write the query and Run it.
PromQL is drawn by the chart (at most 4 expressions, one a line, each its own series), asked
only of a Prometheus data source through Grafana's query endpoint. A LogQL query is asked of
the network's Loki over at most 30 days (Loki answers at most 30 days 1 hour at a time),
through its query endpoints only, waiting at most 1 min 5 s (Loki's default query timeout
and 5 s): a log
query draws its newest 200 lines; a metric query (`count_over_time`, `rate`, `sum by …`) draws
its series on the same chart as a metrics answer, the 20 largest, a point every 5 minutes at
24 h and every hour at 7 or 30 days. Every line and label is masked like every other log line
Mercury shows, and the bounds are said under the answer. A refusal names the bound and what
passed it. A query is at most 2000 characters of printable ASCII. These are reads: nothing is
written, and nothing reaches a device. Its **Source** and **Mode** switches open the builders
described below: the metrics builder (Metrics, Builder) and the logs builder (Logs, Builder).
A builder opened from here starts afresh: it does not read the query in the box back.

**Saved views.** **Save this view…**, beside Copy the link on any answer (Syslog by device
included), asks a title (at most 80 characters) and saves the question as you asked it (the question, its device and
interface, its range, your own query) for everyone on this network, with your name and the
time. The Query tab lists them under **Saved by your team**, pinned first, then the newest:
each opens its question as saved. **Pin** brings a view to the front for everyone and
**Unpin** returns it; **Remove…** asks first, and removes only the saved link: the history it
asks is untouched. A network keeps at most 100. Each save, pin and removal is listed on the
Timeline under **Saved views**. If the saved views' file cannot be read, the tab says so and
nothing can be saved until it is repaired, so no one's views are written over. The sidebar's Logs is the live tail
([Logs](logs)); Syslog by device's "Open these lines on Logs" opens it filtered.

## Ask your own: the logs builder {#ask-logs}

Ask a question of the network's logs by choosing, not by writing LogQL. **Source** switches
between Metrics and Logs and **Mode** between Builder and Code (Code is the box where a query is
written by hand; **Edit as code** hands it the query the builder formed). Each choice is in the
address, so **Copy the link** carries the whole question, and **Save this view…** saves it for
the network like any other view.

- **Ask in words**, at the top of both builders, fills the choices from a question as you
  would say it, through one recorded AI call (see [Ask in words](ask-in-words)). It carries
  the **AI** mark; when hosted AI cannot answer it is disabled with the reason under it, and
  everything below it works as ever (see [The AI mark](installation-settings#ai-mark)).
- **Start from** sets every choice at once to a common question: interfaces going down, OSPF
  adjacency changes, configuration changes and who made them, errors and worse.
- **Kind** offers the values of Loki's `job` label over the range: whatever the network's log
  store holds, read from Loki, never assumed. Choose one or more, or every job.
- **Devices** offers the devices Loki holds lines from in the range (**+ device**), the network's
  roles (**by role**), or **all**. Where Loki's `device` label covers the whole range a device is
  matched by it; a range starting before the label's first line matches each device by its own
  name before the line's timestamp, which reads the older lines too, and the row says which.
- **Severity at or worse than** keeps lines of that severity or worse: by Loki's `severity`
  label where it covers the range, else by the digit in each line's mnemonic (`%LINK-3-UPDOWN`
  is 3). A line with no severity, a trap, is left out once a severity is chosen.
- **Mnemonic** offers the mnemonics Mercury's logs reader counted for the chosen devices over
  the range, the most frequent first; **+ more** lists the rest.
- **Text contains** and **excludes** keep or leave out lines holding the text, exactly as typed.
- **Show** draws the **Lines**, newest first, or **Counts over time**: the matching lines
  counted in each window (a minute to a day), one series per device, mnemonic or any label
  Loki holds, drawn on the same chart as a metrics answer. Click a point to name its window and
  open **Show these lines**: the Lines view for that series in that window.

**The query** is drawn as it forms, the last choice marked, with a sentence saying what that
part does and what the whole query reads. Every value you choose reaches Loki inside one quoted
string, escaped, so a quote, a backslash or a line break in it can never become part of the
query's own structure; a label name, which cannot be quoted, must be one Loki holds. Mercury's
heartbeat lines are always left out.

**Range** is 1 h, 24 h, 7 days, 30 days, or **From… to…**: the last so many minutes, hours or
days, or two times in UTC, your local time shown beside each; Apply or Cancel. The **Bounds**
under it are Loki's own, read from its configuration (the longest span one ask can cover, how
long an ask may take, the most lines and series an ask returns, how long lines are kept) and
Mercury's (200 lines a page, at most 1,000 windows a series, the 20 series with the most lines
drawn).

**Ask** sends the query; the button says **Asking Loki…** until the answer is drawn below it,
and changing any choice afterwards removes the answer, since it no longer matches the query.
The answer is one of: the counts (the chart, then each series' lines in the range, its most in
one window and its last window with a line); the lines (time received, device, severity, kind,
the line masked like every log line Mercury shows, each masked value marked; 200 a page,
**Older ›** for the next and **‹ Newest** back to the first; a line with a masked value offers
**Reveal…**, below);
**Refused**, naming the bound and the range or count that passed it, with the choice that fits;
**Couldn't load**, naming what Loki answered or how long it was waited for, when the live tail
last read Loki well, with **Ask again** (nothing is drawn from an earlier answer);
or **No lines in range**, saying how many lines the same jobs and devices sent in the range and
whether the range is inside what Loki keeps, so an empty answer is not mistaken for a gap, with
**Drop the text filter** when a text filter is set. A
line's time is when the collector received it, never the device's clock. These are reads:
nothing is written, and nothing reaches a device. **Edit as code** from Counts over time opens
Code mode with the count query, drawn there on the same chart.

**Reveal…** on a line asks why you need to see it (at least three words), then reads that one
line from Loki again and draws it unmasked under its masked form, to you only: a verified
person, never a service. Who, when, which line (its stream and time) and the reason are
recorded first and listed on the Timeline under **Reveals**; the value never is.
How it works: [Reveal a log line](reveal-log-line).

## Ask your own: the metrics builder {#ask-metrics}

Ask a question of the network's metrics by choosing, not by writing PromQL. It shares the logs
builder's head (**Source**, **Mode**), its range, its query box and its actions; **Edit as code**
hands the PromQL formed to Code mode. The network's **Saved queries** are listed beside it, each
one click from its answer.

- **Start from** sets every choice at once to a common question: errors per interface (the top
  5), CPU per device over 7 days, BGP sessions not established, bytes in per role. A question
  whose metric Prometheus does not hold is drawn but is not a link.
- **What** searches the metric names Prometheus holds over the range, and their help text, and
  lists the matches, each with its type (counter, gauge) and its unit where one is known. The
  names, help and types are Prometheus's own, never a list Mercury keeps.
- **Devices** offers the values of the `device` label the chosen metric carries (**+ device**),
  its `role` label's values (**by role**), or **all**. **Interfaces** offers the IF-MIB interface
  names it carries (`ifDescr`, else `ifName`); a metric with no such label has no Interfaces row.
- **Filters** keep or leave out series by any label the metric carries: **+ filter** opens the
  editor, a label, how it matches (= is exactly, != is not, =~ matches a pattern, !~ does not; a
  pattern is RE2, anchored at both ends) and a value, with the values the label holds offered
  and how many series the filter would keep or leave out.
- **Operations** apply in order. A counter (Prometheus's metadata says so) always starts with a
  **rate per second** or an **increase** over a window, never its raw value. A gauge (a level or
  a state, such as an interface's status: 1 up, 2 down) may start with **changes**: how many
  times its value changed in the window before each point, never by how much (PromQL's
  `changes()`). Its window is offered up to 90 days, and it starts at the range's own length
  (24 h is 1 day), so the last point is the count over the whole range: "interface status
  changes on one device today" is `changes(ifOperStatus{device="…"}[1d])` over 24 h. It is
  refused on a counter, whose value rises at nearly every scrape, and anywhere but first; a
  metric Prometheus gives no type is offered both. **+ operation** adds
  × 8 (bytes to bits, for a metric counted in bytes), per minute (× 60, after a rate), a group
  (sum, avg, min, max or count, by a label the series still carry), or a comparison that keeps
  only the values equal to, not equal to, above or below a number. The unit follows the chain:
  bytes, × 8 is bits, a rate is per second, changes are counted per window.
- **Top** keeps the 5 or 10 highest series at each step (`topk`); over a range, more than that
  many series can appear.

**The query** is drawn as it forms, the last choice marked, with a sentence saying what that
part does and what the whole query reads. Every value you choose reaches Prometheus inside one
quoted string, escaped, so a quote, a backslash or a line break in it can never become part of
the query's own structure; several values are matched as exact names; a metric or label name,
which cannot be quoted, must be one Prometheus holds.

**Range** is 1 h, 24 h, 7 days, 30 days, 90 days, or **From… to…** (the last so many minutes,
hours or days, or two times in UTC, your local time beside each). The step widens with the
range so that a series is at most 1,000 points (15 s at 1 h to 3 h at 90 days). The limits in
From… to… are Prometheus's own, read from its flags (how long it keeps, how long one ask may
run, how many samples one ask may load), the long-term store Code mode reads past what
Prometheus keeps, Mercury's (1,000 points a series, 200 series an answer, the 20 highest drawn)
and Loki's for the logs builder.

**Ask** sends the query; the button says **Asking Prometheus…** until the answer is drawn, and
changing any choice afterwards removes the answer. The answer is one of: the chart, with each
series' value now and its highest and lowest in the range (past 20 series, the 20 highest are
drawn and the rest counted); **Refused**, naming the bound and what passed it, with the choice
that fits: a rate's or a count of changes' window shorter than two scrapes of the metric's
slowest job, more samples
than Prometheus loads in one ask, more than 200 series; **Couldn't load**, naming what
Prometheus answered (its own words for a query it refused) or how long it was waited for, and
what its probe last found, with **Ask again**; or **No data in range**, saying whether the
range is inside what Prometheus keeps, so no samples is not mistaken for a zero. These are
reads: nothing is written, and nothing reaches a device.

## Baselines {#baselines}

Every baseline: when it was taken, what its commit recorded it earned, and whether it can be
re-applied without changing a credential a device holds now (a baseline older than a
rotation cannot). A withdrawn baseline is drawn with why. The judgement is made in the
background whenever a commit or a tag moves.

**Re-apply…** on a baseline's row opens its re-apply: every device the baseline holds, with
the counts first (will be restored, needs a stated reason, blocked, already as the baseline
holds it, and the devices it predates, left as they are), each device's program and checks
one level down. A device whose program needs a stated reason (a dangerous line, a secret
added back) is not part of the batch: its link opens its own Restore at that baseline, where
each line is given its reason. One confirm restores the rest, one device at a time, each
verified and rolled back alone, its configuration and its intent from the baseline; the batch
is drawn below as it runs. Like every restore it is merge-only: a line the device gained since
the baseline is not removed. See [Restore and re-apply a baseline](restore).

