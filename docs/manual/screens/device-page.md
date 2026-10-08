# The device page

Everything about one device, addressed by its name and its network:
`/v2/device/<name>?list=<network>`, or the network the app is showing when the address names
none. Every link, tab and action on the page keeps that network, so the page never switches to
another network's device of the same name; a confirm sent from a page of another network does
nothing and says so. When the name is not in the network shown but is in one other network,
the page says which, with the link. Its header names the model, platform, address and the
account the tool signs in as; Actions lists the operations on the device.

## Actions {#actions}

Everything is under **Actions**, one menu, Plan a deploy first: Plan a deploy, Capture, Seed
intent, Restore from, Remove lines (Mode B),
Revert intent, Retry rolled-back change, Rotate credential, Persist and Retire. **Capture runs here**: its card takes the place of the
tab you were on, reads the device, and shows what its golden would become, against the golden
now and against committed intent, with the checks and the confirm bound to that read; once you
record it, the same card shows the commit, who and when (the read's timings on hover), what is
still true against intent, and what to do next. **Persist and Rotate run here too**: Persist's card says what the save sends and then reads, what it will not do, its operands and checks, and after the save whether the startup config carries the credential; Rotate's reads the account's line, shows the plan with the new password never shown, and after the confirm waits for the rotation and draws its result with the one next step. **Plan a deploy runs here as well**: its card shows the exact program from committed intent, each dangerous line waiting on your stated reason, the lines left on the device (tick one to remove it, Mode B, with its own reason), what will not happen, the operands and checks, and the confirm bound to that program. While it runs, the card shows the pipeline's stages (done with their times, the one running with what it waits on); after, the result from its receipt, and if verify failed and rolled back, its two ways out (Revert intent, Retry with a reason). **Restore from runs here**: its card lists the moments the device can be restored from (its golden now, its older goldens and the baselines holding it, each with its credential state), then the chosen moment's program, each line waiting on your stated reason (a dangerous line, an account the moment adds back), what stays on the device, the operands and checks, and the confirm bound to that program; it runs as a job, as the deploy does. **Revert intent and Retry rolled-back change run here**, offered only while a rollback's block stands on the device (otherwise each row says why): Revert's card starts on the commit the rollback undid, shows the intent document after the revert, what it will not do (nothing is sent to the device) and the confirm bound to that commit; Retry's shows the blocked program and offers its confirm once you state why the change was right after all, recorded as you say it. **Remove lines (Mode B)** opens the deploy's card at its lines left on the device, highlighted, because removals are made as part of a deploy: tick the lines to remove there, and anything intent adds is sent with them. A device holding nothing removable opens nothing: the row says so in place. A row stays open and busy on itself until its card arrives, and a click made while the page is still loading is kept and carried out once it has. A card refused because another operation holds the device says who, and reads again when the tool announces that operation finished. Cancel or Close puts the tab back. **Seed intent runs here**: its card shows the intent document that would be committed (the first lines of the change, the whole document one click below), whether the template reproduces the device (a line it does not model is named, and blocks a deploy until modelled or acknowledged), the device's own lines (its self-signed trustpoint, certificate bodies and licence UDI, never blocking and never intent), and the confirm bound to the seed; after it, what stays true and the Intent tab or a deploy plan as next steps. **Retire runs here**: its card asks why, lists what retire changes in order, what is generated and so dropped (with when), what survives (with how each is removed) and its checks, and refuses until a break-glass export holds the device's current credential, pointing at Credentials; after it, the result says what was dropped and what is still to remove, and the device's address shows its retired record from then on. **Run a privileged command… runs here** (Tier 2): its card offers clear counters and clear arp-cache on one of the device's own interfaces (the management one never offered), clear logging and undebug all, reads the before-state, and confirms with your reason; the result shows before and after and the verdict ([Run a privileged command](privileged)). Every action under Actions runs here. How each works:
[Deploy a change](deploy), [Capture and Save All](capture), [Remove lines (Mode B)](removal),
[Persist](persist), [Rotate a credential](rotate), [Seed intent](seed),
[Restore and re-apply a baseline](restore), [Revert or retry after a rollback](revert-retry),
[Retire a device](retire).

## Overview {#overview}

What the tool knows about the device, each fact with where it came from: its last golden, its
intent state, whether its golden matches its intent, the monitoring profile it inherits, and
its checks (reachability, Oxidized's copy, alerts).

## Intent {#intent}

The device's intent as committed (a file edited on the host but never committed is never
drawn), its last intent commit, and what the monitoring profile adds. **Edit** opens the
editor in place of the document: checked as you type, what your edit changes and what a deploy
would send, the lines the template does not model with a tick to acknowledge each, and the
commit with your reason. Nothing is sent to the device until you plan a deploy. A device whose
intent is only onboarding's bootstrap has no Edit: seed it first. See
[Edit a device's intent](edit-intent).

## History {#history-tab}

The History page's timeline filtered to this device, over all time. It is the same reader
drawing the same rows, so the two can never disagree; the link at the top opens the History page
filtered to the device. It holds every record the tool keeps about the device:

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
| onboarding | an onboarding or adopt run, with its result |
| acknowledged | a Needs attention row acknowledged, with who and why |
| freshness | a freshness gate authorised for this device, with the reason |
| approval | a queued action approved or rejected |
| break-glass | a break-glass record exported that holds this device (the row names how many devices it holds) |
| cut off | an operation whose process ended mid-run, found when the hold was cleared |

A record that could not be read is said above the timeline: the timeline lacks it, which is
not the same as nothing having happened.

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
reload is, and so is a window the tool was told about beforehand
(`scripts/nmas-planned-restart` on the host). Anything else is unplanned, and is also on Needs
attention for seven days.

## Monitoring {#monitoring-tab}

What the device is monitored by, and its dashboard: the panels of the device dashboard that
select this device, drawn here. A panel that does not apply (telemetry on a switch that
streams none) is folded, with why. A panel folded by a rule about the device's model is
folded only once Grafana, asked as the page is drawn, finds no series for its queries for this
device in the last hour; if one is found, the panel is drawn. Each hidden panel's line says
one reason, its provenance (the rule's measurement, a condition with this device's values) on
hover. An empty panel says what it asked and that nothing matched ("No series matched
ifHCInOctets{device="s1"} in the last 1 h."), with the dashboard's own explanation on hover;
one a known platform limit explains (vIOS reports no memory pool or platform CPU) leads with
that reason instead, the query on hover. A range longer than the live store keeps (90 days by
default) is read from the history store when one is set (Thanos, for example), and each panel's
foot line says so; with none set, such a range is refused, naming the setting.

## Logs {#logs-tab}

The device's syslog for the last 24 hours, from Loki. Heartbeats are folded into a count; an
error that names the heartbeat is still listed.

## NetBox {#netbox-tab}

The device's NetBox record, read-only, and who owns it: {{product}} created it, {{product}} adopted it, or a
person's. {{product}}'s recorded writes to it are listed.

## Neighbours {#neighbours}

The routing adjacencies the network's committed intent implies for this device, against what
Prometheus last read from its routing tables: up, down with its state, unexpected, or not
measured. It opens no session to the device.

## Ask the device {#ask-the-device}

Ask the device a Tier 1 command and read its answer here: a `show`, a bounded `ping` or
`traceroute`, `dir` or `more` of its own storage, `verify /md5`, a `send log` line, or a
terminal setting ([the command policy](show-commands#tiers)). Type a command, or pick one of
the common reads or a saved set. The command is checked as you type: a command outside Tier 1
(`reload`, `copy`, `clear counters`, `| redirect`, anything no tier holds) says beside the box
which tier it is in and where to go instead, and **Run** stays off; a command known to be heavy (`show tech-support`, `show logging`
unfiltered) says what it costs. **Run** reads the device now, busy on itself until the answer
arrives, which appears in place: masked as a golden is, with how long it took, and who and
when on hover. An answer longer than the network's cap is kept to the cap and says it was cut.

The device is held while it is read, so a read and another operation never touch it at once:
a device another operation holds is not read (the card says who holds it; run it again once
that ends), and while a read holds it, a deploy is refused naming the read.

**Recent reads** lists the device's latest runs, yours and others' (and the agent's, for the
person it acted for), each with its outcome; **Open** draws one again. **Compare with the last
answer** shows the lines that changed since the device last answered the same command.

Nothing here changes the device: there is no configuration mode and no free-form session. Every
read is recorded. How it works: [Show commands](show-commands).
