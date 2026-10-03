# Monitoring

The fleet's monitoring, in two tabs.

## Dashboards {#dashboards}

The network's fleet dashboard from Grafana, drawn here: the panels the app can draw are drawn
with the dashboard's own queries; those it cannot (alert lists, text, logs) keep their place
and link to Grafana. Another dashboard can be chosen for the view without changing the
setting.

## The time range {#time-range}

One click for the last hour, 6 hours, 24 hours or 7 days, or type a range ("last 90
minutes", "3d"). Prometheus keeps 90 days: a longer range is refused at the control, naming
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
- **Blank:** not applicable to the device or its platform.

IP SLA's ring links to the IP SLA page for that device, where probes are suggested.

To deploy, tick devices in the left column. A device is offered only when the monitoring profile
supplies something it is missing. A device with nothing to deploy has a faded box that says why
when you hover over it. The bar above the grid names the devices you ticked and how many missing
templates the profile supplies for them, and it updates as you tick. **Deploy missing
templates…** opens the preview for those devices. **Clear** unticks them all. The box in the
header ticks every device that can be ticked. How the deploy works:
[Apply a monitoring template](monitoring-templates).

A configured cell can still be **not reporting**: the configuration is there and its data is
not arriving. The cell says for how long ("no scrape for 12 min", "no stream for 9 min",
"none for 16 min") and links to the device tab where the cause is found: Monitoring for SNMP,
IP SLA and telemetry, Logs for syslog and the heartbeat. A deploy does not fix it, so a
not-reporting cell is never offered for Apply. A reader asks Prometheus and Loki every minute,
with one query per source for the whole fleet:

- **SNMP and IP SLA:** the device's targets in Prometheus, and the last time each one was
  scraped. A target that fails, or that has not been scraped for two of its intervals, is not
  reporting. The cell names the failing job when only some of the device's jobs fail.
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
