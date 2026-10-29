# The device page

Everything about one device, addressed by its name and its network:
`/v2/device/<name>?list=<network>`, or the network the app is showing when the address names
none. Every link, tab and action on the page keeps that network, so the page never switches to
another network's device of the same name; a confirm sent from a page of another network does
nothing and says so. When the address names no network and the name is not in the network
shown, the page says which other network holds it, with the link, or lists each network that
does; an address that names a network where the name is not says only that. Its header names
the model, platform, address and the account the tool signs in as; Actions lists the
operations on the device.

## Actions {#actions}

Everything is under **Actions**, one menu, Plan a deploy first: Plan a deploy, Capture, Seed
intent, Restore from, Remove lines (Mode B),
Revert intent, Retry rolled-back change, Rotate credential, Persist, Run a privileged command,
Reload and Retire. **Capture runs here**: its card takes the place of the
tab you were on, reads the device, and shows what its golden would become, against the golden
now and against committed intent, with the checks and the confirm bound to that read; once you
record it, the same card shows the commit, who and when (the read's timings on hover), what is
still true against intent, and what to do next. **Persist and Rotate run here too**: Persist's card says what the save sends and then reads, what it will not do, its operands and checks, and after the save whether the startup config carries the credential; Rotate's reads the account's line, shows the plan with the new password never shown, and after the confirm waits for the rotation and draws its result with the one next step. **Plan a deploy runs here as well**: its card shows the exact program from committed intent, each dangerous line waiting on your stated reason, the lines left on the device (tick one to remove it, Mode B, with its own reason), what will not happen, the operands and checks, and the confirm bound to that program. While it runs, the card shows the pipeline's stages (done with their times, the one running with what it waits on); after, the result from its receipt, and if verify failed and rolled back, its two ways out (Revert intent, Retry with a reason). **Restore from runs here**: its card lists the moments the device can be restored from (its golden now, its older goldens and the baselines holding it, each with the message recorded with it and its credential state), then the chosen moment's program, each line waiting on your stated reason (a dangerous line, an account the moment adds back), what stays on the device, the operands and checks, and the confirm bound to that program; it runs as a job, as the deploy does. **Revert intent and Retry rolled-back change run here**, offered only while a rollback's block stands on the device (otherwise each row says why): Revert's card starts on the commit the rollback undid, shows the intent document after the revert, what it will not do (nothing is sent to the device) and the confirm bound to that commit; Retry's shows the blocked program and offers its confirm once you state why the change was right after all, recorded as you say it. **Remove lines (Mode B)** opens the deploy's card at its lines left on the device, highlighted, because removals are made as part of a deploy: tick the lines to remove there, and anything intent adds is sent with them. A device holding nothing removable opens nothing: the row says so in place. A row stays open and busy on itself until its card arrives, and a click made while the page is still loading is kept and carried out once it has. A card refused because another operation holds the device says who, and reads again when the tool announces that operation finished; a Rotate card freed by a rotation that ran meanwhile shows that rotation's result, never a second offer to rotate. Cancel or Close puts the tab back. **A Rotate, Plan a deploy, Restore or Reload you left running opens again here**: the page opened while one runs on the device, or after one finished that you have not seen, shows its card in place of the tab, saying it was reopened and when, whether you came from the top bar's In progress chip, a bookmark or the Devices list ([What is running now](getting-started#in-progress)). **Seed intent runs here**: its card shows the intent document that would be committed (the first lines of the change, the whole document one click below), whether the template reproduces the device (a line it does not model is named, and blocks a deploy until modelled or acknowledged), the device's own lines (its self-signed trustpoint, certificate bodies and licence UDI, never blocking and never intent), and the confirm bound to the seed; after it, what stays true and the Intent tab or a deploy plan as next steps. **Retire runs here**: its card asks why, lists what retire changes in order, what is generated and so dropped (with when), what survives (with how each is removed) and its checks, and refuses until a break-glass export holds the device's current credential, pointing at Credentials; after it, the result says what was dropped and what is still to remove, and the device's address shows its retired record from then on. **Run a privileged command… runs here** (Tier 2): its card offers clear counters and clear arp-cache on one of the device's own interfaces (the management one never offered), clear logging and undebug all, reads the before-state, and confirms with your reason; the result shows before and after and the verdict ([Run a privileged command](privileged)). **Reload… runs here**: its card reads the device and draws five checks by name (it boots what it runs, its golden and intent, startup carries Mercury's credential, the boot image, nothing holds it) with what else Mercury loses reach to while it restarts shown first; you confirm with a reason; the run declares its planned-restart window before anything is sent, then reloads, waits and checks it came back running what it ran, on the one stepper ([Reload a device](reload)). Every action under Actions runs here. How each works:
[Deploy a change](deploy), [Capture and Save All](capture), [Remove lines (Mode B)](removal),
[Persist](persist), [Rotate a credential](rotate), [Seed intent](seed),
[Restore and re-apply a baseline](restore), [Revert or retry after a rollback](revert-retry),
[Run a privileged command](privileged), [Reload a device](reload), [Retire a device](retire).

A device whose SSH host key changed is re-keyed on its page: Needs attention's row opens the
Re-key card in place of the tab ([Re-key a device](rekey)); it is not on the Actions menu. The **Drained** badge beside its name in the header is switched
off for now (see [Devices](devices#drained)).

## Overview {#overview}

What the tool knows about the device, each fact with where it came from: its last golden, its
intent state (the state the Devices list shows for it, from its last measurement, or "intent
changed since measured" when its intent, the profile or the template library has moved since),
whether it is answering, the monitoring profile it inherits, and its checks: **Since last
capture** (the drift check's), **Intent** (whether its golden matches its intent now), **Reboot-safe** (whether the hourly
startup check found its startup config carrying its credential), **Credential** (how long since
Mercury last rotated it, or "never rotated by Mercury", and when its profile's rotation policy
next makes it due; see [on a schedule](rotate#scheduled)) and **Alerts**. For a network that
takes Default's monitoring profile, the profile line does not yet name Default's (a gap,
registered, C1362).

**Since last capture** is the network's last drift run's word on the device, the device
against its golden, named for what it compares (a golden is the record of its last capture):
unchanged at the last run, skipped, or changed, with how many lines it differs from its golden
by. It never says whether the device is right: that is **Intent**. When its last capture took
in a change made outside Mercury that departs from intent by a line no rule explains, the row
says so and is a warning, never a pass: "unchanged at the last run, but its last capture
(`<commit>`) took in a change made outside Mercury that departs from intent (+1 -1): changed
out-of-band, by console per SYS-5-CONFIG_I; it is not at its intent (see Intent)" (how it was
changed is the device's own log line, kept with the capture; see
[Drift](drift#out-of-band)). A drift record that cannot be read says **unreadable** with the
reason: whether the device is at its golden is then not known, which is neither unchanged nor
"no drift run recorded". A changed row opens, in place, onto three parts, read when you open it
(nothing is read from the device):

- **The lines**: the difference the drift run kept, its golden (`-`) against what it ran (`+`),
  every line masked as every other screen masks configuration (a value in a secret's position
  reads `<redacted:…>`; how many lines carry one is said). The run that kept them is named, and
  when the last run counted a different number of lines the part says the device may have moved
  since: the drift queue keeps the first run's difference while its item waits. Once the item
  is withdrawn, closed or expired (48 hours), the lines are not kept, and the part says why.
- **What its log says**: the device's own lines since its golden was recorded (at most 30 days
  back, newest first, 50 at most) in which it was configured (`%SYS-5-CONFIG_I`,
  `%SYS-5-CONFIG_P`, a logged command) or restarted (`%SYS-5-RESTART`, `%SYS-5-RELOAD`), each
  at the time Mercury received it, the device's own time on hover (a clock IOS marks as not set
  is said). Loki not answering is "Couldn't load", never "no lines"; the Logs tab has every line.
- **What to do**: keep it (**Capture**, its golden becomes what it runs), put intent back
  (**Plan a deploy…**) or remove lines (**Remove lines (Mode B)…**), each opening the device
  page's own card as the Actions menu does. A deploy is planned against the golden, and a
  drifted device has moved since it, so capture first: a deploy planned before is refused at
  apply with nothing sent ([Deploy a change](deploy), [Capture and Save All](capture),
  [Remove lines (Mode B)](removal)).

**Intent** names the lines on the device that intent lacks and the lines in intent the device
lacks, masked. Where a rule explains some of them, the row says so after its lines, each class
with its count ("By rule: 2 lines: VLANs a VTP server switch keeps in vlan.dat, never in its
configuration; 1 line: not explained by a rule"). Where no rule explains any of them, the row
says **No rule explains this difference**, so a departure nothing accounts for is never read as
one a rule does. The rules: VLAN lines intent has on a switch
whose VTP mode is server or client (such a switch keeps its VLANs in its VLAN database and never
prints them, so its golden cannot hold them; the mode is read from the golden's capture header
or its `vtp mode` line, and when neither says, the VLAN lines stay unexplained); a section
holding the same lines in another order (in an access list or route map that order is a real
change); a line Mercury does not model, said with where it is carried: verbatim in intent's
not-modelled list, or only in the device's golden (a line on the device that intent does not
carry at all, kept by adding it to intent's not-modelled list or removed in a Mode B plan); and
the device's own self-signed certificate. A class explains a difference and never clears it: the row stays a
departure until the golden matches intent. Whether a VTP switch has a VLAN is read with
`show vlan id <N>` in [Show commands](show-commands).

## Intent {#intent}

The device's intent as committed (a file edited on the host but never committed is never
drawn), its last intent commit, and what the monitoring profile adds. **Edit** opens the
editor in place of the document: checked as you type, what your edit changes and what a deploy
would send, the lines the template does not model with a tick to acknowledge each, and the
commit with your reason. Nothing is sent to the device until you plan a deploy. A device whose
intent is only onboarding's bootstrap has no Edit: seed it first. See
[Edit a device's intent](edit-intent).

A document laid out by hand cannot be patched, so the tab says "This document is
hand-formatted" above it and offers **Normalise the formatting…**: the editor opens on
Mercury's own formatting of it, nothing written, and its check proves the change is formatting
only (the parsed document equal, the render byte-identical, the device diff empty, the masked
lines identical by keyed hash, the new text round-tripping) before **Commit the formatting
only** is offered. Any line that differs stops the commit and is listed, masked. See
[Normalise the formatting](edit-intent#normalise).

**Change it in words** (marked **AI**), above the document, drafts a change from a sentence
("shut G4", "describe the host port as desk 4", "add VLAN 40 named LAB") and shows it in the
editor's own preview: how your words were read, the changes, what a deploy would send, the
checks. When a name could mean several ports, it asks which first. Nothing is written until
you press **Commit this draft** (or **Commit and plan deploy**, which opens the deploy
preview next); **Discard draft** drops it. It changes this device only, and only the
interfaces, VLANs and networks your sentence names. See [Change it in words](intent-in-words).

## History {#history-tab}

The History page's timeline filtered to this device, over all time. It is the same reader
drawing the same rows, so the two can never disagree; the link at the top opens the History page
filtered to the device. It shows the newest 50 records; **Load more**, under the last, reads
the next 50 older than it and draws them in place (busy, "Loading…", until they arrive), and the
device page's address takes the place it reached (`before=`), so Back and a shared link return
there, with **Back to the newest** above the records. **Jump to** a day and **Go** start the tab
at the end of that day (UTC; `on=`), keeping the kind chosen. Paging works as on the History
page: [Load more and Jump to](history#timeline).

Above the records, one click chooses a kind: **All**, **Goldens**, **Intent**, **Deploys and
restores**, **Measured, unchanged** or **Restarts**. The kind is chosen before the newest 50 are
cut, so the device's goldens are all reachable under **Goldens** even when a daily Save All has
written a newer "measured" row every day since. The choice is part of the page's address
(`?tab=history&kind=golden`), so it survives a reload and can be shared, and the link to the
History page carries it. A kind with no record for the device says so ("No record of the kind
chosen (Restarts) for edge1"), with **Every kind** beside it; a kind the tool does not know is not
applied and is said by name above the records.

It holds every record the tool keeps about the device:

| Kind | What it is |
|---|---|
| golden | a golden commit, naming its workflow (capture, save, deploy, restore) and who |
| measured | a save that read the device and found its golden unchanged |
| intent | an intent commit, with who and which operation made it |
| receipt | a deploy, restore, removal or rollback, with its result |
| restart | a restart, planned or not, with the device's own reason |
| window | a planned-restart window declared for the device |
| rotation | a credential rotation, its persistence or a recovery, with the step it stopped at if it failed |
| persist | the device's own save, and whether its startup config read back carrying the running credential; a save never claims a rotation |
| retry | a retry authorised after a rollback, with the reason |
| privileged | a privileged command (Tier 2) run on it, with before and after |
| reload | a reload, with who, why, its window and each step's outcome |
| onboarding | an onboarding or adopt run, with its result |
| acknowledged | a Needs attention row acknowledged, with who and why |
| hostkey | an SSH host key kept, replaced or forgotten for it, or a planned window's new keys |
| reveal | a secret or configuration of it revealed, with who |
| show commands | a Show commands run that read it |
| heartbeat | its heartbeat alert rule re-measured |
| approval | a queued action approved or rejected |
| break-glass | a break-glass record exported that holds this device (the row names how many devices it holds) |
| cut off | an operation whose process ended mid-run, found when the hold was cleared |

A record that could not be read is said above the timeline: the timeline lacks it, which is
not the same as nothing having happened. On a network with no repository yet, the tab says so
once instead ("No repository yet: the network's first commit makes it"), naming the device's
records the repository will hold: its golden and intent histories and its measured saves.

Each entry is one line: when, its kind, its device or devices, what, any marks (corrected, acknowledged, crash file, record known
wrong, failed) and who. Open it for the full record underneath: the reason, each step and its
result, the correction or acknowledgement with who and why, and how the person was identified.
A failed rotation, save, onboarding run or deploy is drawn red.

A record known to be wrong is never rewritten. It is drawn as what is known, marked
**corrected** or **record known wrong**, with what it recorded and why underneath. For
example, saves recorded before 2026-10-03 carried a rotation's state, and are drawn as saves.

Every operation that can change a device declares which of these records it writes, and the
test suite fails when a new one declares none, so an operation's result is readable here later,
not only on its result card now.

A restart is found where the device's uptime counter fell (SNMP, read each minute), never by
subtracting its uptime from the clock: a slow device clock runs its uptime slow too, so that
subtraction places a restart hours from where it was. Each shows the device's own reason for
its last reload and the crash file it saved, if any, and whether it was planned: the tool's own
reload is, and so is a window the tool was told about beforehand. v2's only control that
declares such a window is the device's own **Reload…**; a restart made any other way can be
declared beforehand only outside the interface (a gap, registered, C1361). Anything else is
unplanned, and is also on Needs
attention for seven days. A device that is down is not read, so its readings around a restart
have a gap as long as the restart; the restart is found by comparing its newest reading with
the one read before the gap, however long it was gone. While a planned window lasts, the
header reads "Restarting as planned (until …, by …)" in place of "Not answering".

## Monitoring {#monitoring-tab}

What the device is monitored by, and its dashboard. The **Monitored by** card names each
integration the network uses and what the device's committed golden holds for it (Coverage's
own cells, in words): configured, missing, excluded with why, not applicable. When the
network's monitoring profile supplies something it lacks, **Apply monitoring profile…** opens
the preview of exactly what would be sent ([Apply a monitoring template](monitoring-templates));
otherwise the card says why it cannot be applied, or that the device is configured for
everything the network uses. Below it, the panels of the device dashboard that select this
device, drawn here, with the same range controls as Monitoring's Dashboards. A panel that does not apply (telemetry on a switch that
streams none) is folded, with why. A panel folded by a rule about the device's model is
folded only once Grafana, asked as the page is drawn, finds no series for its queries for this
device in the last hour; if one is found, the panel is drawn. Each hidden panel's line says
one reason, its provenance (the rule's measurement, a condition with this device's values) on
hover. An empty panel says what it asked and that nothing matched ("No series matched
ifHCInOctets{device="edge1"} in the last 1 h."), with the dashboard's own explanation on hover;
one a known platform limit explains (vIOS reports no memory pool or platform CPU) leads with
that reason instead, the query on hover. A range longer than the live store keeps (90 days by
default) is read from the history store when one is set (Thanos, for example), and each panel's
foot line says so; with none set, such a range is refused, naming the setting.

## Logs {#logs-tab}

The device's syslog for the last 24 hours, from Loki. Heartbeats are folded into a count; an
error that names the heartbeat is still listed.

Which of Loki's jobs holds the syslog is read from Loki, never set: every job whose lines carry
a device's syslog form (its own name, its time and a mnemonic) in the last 24 hours, asked at
most once an hour. When no job holds one, the tab says so in place of the lines.

## NetBox {#netbox-tab}

The device's NetBox record, and who owns it: {{product}} created it, {{product}} adopted it, or a
person's. {{product}}'s recorded writes to it are listed, and **Open in NetBox** opens the
record there. A device NetBox does not hold says so.

Below the record, whether NetBox holds what the device's committed golden describes, as the
reader last compared them (with when): "NetBox holds less than edge1's committed
configuration: 1 interface, 2 addresses, 1 cable to add", with **What NetBox lacks** listing
each one. Otherwise it says NetBox holds them, or why it is not known (NetBox not configured,
the network not in NetBox). The same comparison is a [Needs attention](needs-attention) row.

**Import into NetBox…** previews the import of this device alone. It is the NetBox page's own
import, scoped to the device, against the real NetBox and writing nothing. Its card draws
below the record. From your press until it draws, the button says **Starting the dry run…**.
The card lists every object it would create or change, including each cable from LLDP between
this device and another managed device, and each LLDP neighbour it does not make a cable to,
with why. Confirm with **Import**: the plan is recomputed for this device and compared with
the one you saw, and only then written ([how](netbox-import#one-device)). Removing stays on
the NetBox page.

When a retired record (Decommissioning) still holds the device's management address, the
import's card says so, naming the record, and offers **Free <address> from <record>…**. Its
own preview lists each address on that record: deleted if {{product}} created it, otherwise
unassigned and kept in NetBox, with the record's primary addresses cleared. Confirm with
**Free <address>** (busy as **Freeing…**). The card then offers **Preview the import of
<device> again…** ([how](netbox-import#free-address)).

## Neighbours {#neighbours}

The routing adjacencies the network's committed intent implies for this device, against what
Prometheus last read from its routing tables (OSPF, OSPFv3, BGP): up, down with its state,
unexpected, or not measured. RIP and RIPng keep no neighbour table, so their rows come from
what the device hears, as the RIP reader last read it (every 5 minutes, two show commands on
each device whose intent runs RIP): up when this device hears the neighbour, not heard (and
whether the neighbour still hears this device), a speaker intent does not explain as
unexpected, and not measured when the reader could not read the device or its last read is
older than its promise. Opening the tab opens no session to the device.

**Reported** is when the device's routing table was read. A protocol counts as measured when
any of its scrapes in the last 5 minutes answered, so one failed scrape does not blank it; but
when the newest value is older than a scrape and its timeout (90 seconds), the scrapes since
have failed, and the protocol says **As of HH:MM UTC** above its table, each row "as of" its
time: the last good report, never shown as what the device holds now. Needs attention says
the same on a link it judged from such a report.

## Ask the device {#ask-the-device}

Ask the device a Tier 1 command and read its answer here: a `show`, a bounded `ping` or
`traceroute`, `dir` or `more` of its own storage, `verify /md5`, a `send log` line, or a
terminal setting ([the command policy](show-commands#tiers)). Type a command, or pick one of
the common reads or a saved set. The command is checked as you type: a command outside Tier 1
(`reload`, `copy`, `clear counters`, `| redirect`, anything no tier holds) says beside the box
which tier it is in and where to go instead, and **Run** stays off; a `send log` at level 0 to
3 brings a reason field under the box, and **Run** stays off until the reason has three words
(the reason is recorded with the read and shown beside its answer); a command known to be heavy (`show tech-support`, `show logging`
unfiltered) says what it costs. **Run** reads the device now, busy on itself until the answer
arrives, which appears in place: masked as a golden is, with how long it took, and who and
when on hover. An answer longer than the network's cap is kept to the cap and says it was cut.

The device is held while it is read, so a read and another operation never touch it at once:
a device another operation holds is not read (the card says who holds it; run it again once
that ends), and while a read holds it, a deploy is refused naming the read.

**Recent reads** lists the device's latest runs, yours and others' (and the agent's, for the
person it acted for), each with its outcome; **Open** draws one again.
**Compare with the last answer** shows the lines that changed since the device last answered the same command.

Nothing here changes the device: there is no configuration mode and no free-form session. Every
read is recorded. How it works: [Show commands](show-commands).
