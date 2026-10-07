# Monitoring

The fleet's monitoring, in two tabs.

## Dashboards {#dashboards}

The network's fleet dashboard from Grafana, drawn here: the panels the app can draw are drawn
with the dashboard's own queries; those it cannot (alert lists, text, logs) keep their place
and link to Grafana. Another dashboard can be chosen for the view without changing the
setting.

## Which network {#network}

Monitoring shows one network at a time, named in the page's title, and the address carries it
(`/v2/monitoring?list=Branch`), so a copied link shows the same network to whoever opens it.
With no network in the address, the page shows the active list. The Network menu lists every
network. Choosing one opens that network's Monitoring.

Everything on the Dashboards tab is that network's:
- its fleet dashboard (Fleet dashboard UID, in its settings);
- the Grafana it reads, named under the toolbar ("from Default's Grafana, which Lab-3
  inherits" when the network has not set its own);
- that Grafana's dashboards and data;
- its live store's retention and its history store.

A network that declared Grafana not applicable says so instead of drawing anything. A
network whose Grafana is its own and names none (a standalone network that has not configured
it) says "Grafana is not configured" for it, with a link to the network's Settings, where it
can be configured or chosen to inherit Default's (see [Inherit or stand alone](settings-switch)).
A device's Monitoring tab works the same way for the device's own network, and has no network
menu, because a device belongs to one network.

Coverage shows the active list, which its title names. Choosing a network there arrives
with Coverage's batch Apply, which writes to the list it shows.

## The time range {#time-range}

One click for the last hour, 6 hours, 24 hours or 7 days, or type a range ("last 90
minutes", "3d"). The live store keeps 90 days (`metrics_live_retention_days`): a longer range
is read from the history store when one is set (`grafana_history_datasource_uid`, Thanos for
example), each panel's foot line saying so, and is otherwise refused at the control, naming
the limit, and never trimmed, because a trimmed answer would read as the whole range. Each
panel asks for at most 1,000 points, so the step between them widens with the range (15 s
for an hour); hover the range to see the step. The same controls are on a device page's
Monitoring tab.

## Coverage {#coverage}

Every device against every monitoring section, read from each device's committed golden. The
line above the grid gives the answer first: how many devices are fully covered, how many
templates are missing, and how many are not reporting.

Each cell is an icon. Hover over it to see why:

- **A tick:** configured.
- **A quiet ring:** not configured.
- **An amber mark:** configured but not reporting (see below).
- **A red warning mark:** not rendered. The profile supplies the section, but the device's
  template renders none of it (an older shipped template), so Apply cannot send it. It links
  to Templates, where the shipped version is brought in.
- **Blank:** not applicable to the device or its platform.

IP SLA's ring links to the IP SLA page for that device, where probes are suggested. The last
column, Mgmt sources, is the profile's management section: `ip tftp source-interface` and
`ip ssh source-interface` on the management interface, configured when the golden holds both.

The columns are SNMP, Syslog, Heartbeat, NTP, LLDP, Telemetry and IP SLA. NTP's server lines and
LLDP's `lldp run` are read from the golden. A golden with no `lldp run` means LLDP is off only
where that platform's default has been measured as off. Where the default has not been measured,
the cell reads unknown, never "not configured". Whether NTP synchronises and whether LLDP finds
neighbours is not read here yet. Their hover says so, and they are never marked not reporting.

To deploy, tick devices in the left column. A device is offered only when something it is
missing can be sent: a line the monitoring profile supplies, or an IP SLA probe committed to
its intent and not yet on the device. A device with nothing to deploy has no box: hover over
the empty space where its box would be to see why. When no device has anything to deploy, a
note beside the grid says so, and names any device whose IP SLA probe is not chosen yet: a
probe's target is chosen on the IP SLA page, and once committed it is deployed from here. The
bar above the grid names the devices you ticked and how many missing templates they have, and
it updates as you tick. **Deploy missing templates…** opens the combined deploy for those
devices: one program per device, every template it is missing. **Clear** unticks them all.
The box in the header ticks every device that can be ticked. How the deploy works:
[Deploy missing templates](monitoring-templates#combined).

A configured cell can still be **not reporting**: the configuration is there and its data is
not arriving. The cell says for how long ("no scrape for 12 min", "no stream for 9 min",
"none for 16 min") and links to the device tab where the cause is found: Monitoring for SNMP,
IP SLA and telemetry, Logs for syslog and the heartbeat. A deploy does not fix it, so a
not-reporting cell is never offered for Apply. A reader asks Prometheus and Loki every minute,
with one query per source for the whole fleet:

- **SNMP and IP SLA:** the device's targets in Prometheus, and the last time each one was
  scraped. A target with no successful scrape for two of its intervals, and never less than
  3 minutes, is not reporting. One or two missed scrapes, which routers have for about a minute
  now and then, are not. The cell names the failing job when only some of the device's jobs fail.
- **Telemetry:** no series from the device for 5 minutes.
- **Heartbeat:** no beat within the window of the device's own heartbeat alert (each window is
  measured from that device's beats). When no alert rule is installed, the window is twice the
  heartbeat period.
- **Syslog:** for a device with a heartbeat, no line within the same window. Without a
  heartbeat, nothing proves the path works, and a quiet device sends nothing. The cell then says
  "nothing proves it arrives" and never "not reporting".

Hover a configured cell to see when its data last arrived. If the reader has no current
reading, or could not ask a source, the page says so once. The affected cells stay
"configured" and accuse no device of the reader's failure.
