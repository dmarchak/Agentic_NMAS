# The device page

Everything about one device, addressed by its name. Its header names the model, platform,
address and the account the tool signs in as; Actions lists the operations on the device.

## Actions {#actions}

Plan a deploy, and under Actions: Capture, Restore from, Remove lines (Mode B), Seed intent,
Rotate credential, Persist and Retire. **Capture runs here**: its card takes the place of the
tab you were on, reads the device, and shows what its golden would become, against the golden
now and against committed intent, with the checks and the confirm bound to that read; once you
record it, the same card shows the commit, who and when (the read's timings on hover), what is
still true against intent, and what to do next. **Persist runs here too**: its card says what the save sends and then reads, what it will not do, its operands and checks, and after the save whether the startup config carries the credential. Cancel or Close puts the tab back. The others
open on today's device page until the redesign carries each (plan 7.3). How each works:
[Deploy a change](deploy), [Capture and Save All](capture), [Remove lines (Mode B)](removal),
[Persist](persist), [Rotate a credential](rotate), [Seed intent](seed),
[Restore and re-apply a baseline](restore), [Retire a device](retire).

## Overview {#overview}

What the tool knows about the device, each fact with where it came from: its last golden, its
intent state, whether its golden matches its intent, the monitoring profile it inherits, and
its checks (reachability, Oxidized's copy, alerts).

## Intent {#intent}

The device's intent as committed (a file edited on the host but never committed is never
drawn), its last intent commit, and what the monitoring profile adds. Read-only; editing is on
today's page until plan 7.3.

## History {#history-tab}

One timeline for the device: its golden commits (each naming its workflow and who), its intent
commits, its deploy and restore receipts, and every restart. A record that could not be read is
said.

Each entry is one line: when, what, any marks (corrected, acknowledged, crash file, record known
wrong) and who. Open it for the full wording underneath: the reason, the correction or
acknowledgement with who and why, and how the person was identified.

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
streams none) is folded, with why.

## Logs {#logs-tab}

The device's syslog for the last 24 hours, from Loki. Heartbeats are folded into a count; an
error that names the heartbeat is still listed.

## NetBox {#netbox-tab}

The device's NetBox record, read-only, and who owns it: NMAS created it, NMAS adopted it, or a
person's. NMAS's recorded writes to it are listed.

## Neighbours {#neighbours}

The routing adjacencies the network's committed intent implies for this device, against what
Prometheus last read from its routing tables: up, down with its state, unexpected, or not
measured. It opens no session to the device.

## Ask the device {#ask-the-device}

Not built yet (plan 7.3): an allowlisted, read-only command box.
