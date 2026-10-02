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

Every device against every monitoring section, read from each device's committed golden, and
the batch Apply for the devices the profile would fix. How Apply works:
[Apply a monitoring template](monitoring-templates).
