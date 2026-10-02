# Monitoring

The fleet's monitoring, in two tabs.

## Dashboards {#dashboards}

The network's fleet dashboard from Grafana, drawn here: the panels the app can draw are drawn
with the dashboard's own queries; those it cannot (alert lists, text, logs) keep their place
and link to Grafana. Another dashboard can be chosen for the view without changing the
setting.

## Coverage {#coverage}

Every device against every monitoring section, read from each device's committed golden, and
the batch Apply for the devices the profile would fix. How Apply works:
[Apply a monitoring template](monitoring-templates).
