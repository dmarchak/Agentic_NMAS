# Monitoring

The fleet's monitoring, in four tabs: **Dashboards**, **Coverage**, **Profile** and **Alerts**.

## Dashboards {#dashboards}

The network's fleet dashboard from Grafana, drawn here: the panels the app can draw are drawn
with the dashboard's own queries; those it cannot (alert lists, text, logs) keep their place
and link to Grafana. Another dashboard can be chosen for the view without changing the
setting.

## Which network {#network}

Monitoring shows one network at a time, named in the page's title, and the address carries it
(`/v2/monitoring?list=Branch`), so a copied link shows the same network to whoever opens it.
With no network in the address, the page shows the one you chose in the top bar's Network
picker (the installation's current one until you choose). Choosing another there opens that
network's Monitoring.

Everything on the Dashboards tab is that network's:
- its fleet dashboard (Fleet dashboard UID, in its settings);
- the Grafana it reads, named under the toolbar ("from Default's Grafana, which Branch
  inherits" when the network has not set its own);
- that Grafana's dashboards and data;
- its live store's retention and its history store.

A network that declared Grafana not applicable says so instead of drawing anything. A
network whose Grafana is its own and names none (a standalone network that has not configured
it) says "Grafana is not configured" for it, with a link to the network's Settings, where it
can be configured or chosen to inherit Default's (see [Inherit or stand alone](settings-switch)).
A device's Monitoring tab works the same way for the device's own network, and has no network
menu, because a device belongs to one network.

Coverage and Profile have no network menu of their own: each shows the network chosen in the
top bar's Network picker, which its title names, and what they deploy or commit is that
network's.

## The time range {#time-range}

One click for the last hour, 6 hours, 24 hours or 7 days, or type a range ("last 90
minutes", "3d"). The live store keeps 90 days unless the network's settings say otherwise
(`metrics_live_retention_days`): a longer range
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
  template renders none of it (an older shipped template), so nothing can send it. It links
  to Templates, where the shipped version is brought in.
- **n/a:** not applicable: the profile scopes the section away from the device's platform or
  role (telemetry on an IOS switch), or the network has no connector for it. Hover the cell for
  which. A cell is never blank.
- **declined:** a person declined the section on this device. Hover the cell for who, when and
  why; click it to reach its **Undo decline…** row under the grid. On Monitoring › Profile, the
  section's count says it too ("8 of 9 hold it · 1 declined").

Under the grid, **What is not covered, and why** lists each device whose IP SLA is not in its
intent, with the IP SLA page's own words for it: the probe it would suggest, or why it suggests
none. **Add to intent…** opens the IP SLA page for the device; **Decline…** records that you
choose not to fill the gap, with your reason, in the device's intent (How it works: Decline a
monitoring section on one device). A declined section is drawn **Declined**,
with who, when and why, and **Undo decline…**. The summary counts it as declined, never as
covered or missing, and the IP SLA page suggests nothing for it.

IP SLA's ring links to the IP SLA page for that device, where probes are suggested. The last
column, Mgmt sources, is the profile's management section: `ip tftp source-interface` and
`ip ssh source-interface` on the management interface, configured when the golden holds both;
it is configuration only, never judged as reporting or not.

The columns are SNMP, Syslog, Heartbeat, NTP, LLDP, Telemetry and IP SLA. NTP's server lines and
LLDP's `lldp run` are read from the golden. A golden with no `lldp run` means LLDP is off only
where that platform's default has been measured as off. Where the default has not been measured,
the cell reads unknown, never "not configured". Whether NTP synchronises and whether LLDP finds
neighbours is not read here yet. Their hover says so, and they are never marked not reporting.

To deploy, tick devices in the left column; the devices that can be ticked arrive ticked. A
device is offered only when something it is missing can be sent: a line the monitoring profile supplies, or an IP SLA probe committed to
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
not-reporting cell is never offered for a deploy. A reader asks the network's Prometheus and
Loki every minute (its own, or Default's when it inherits them), with one query per source
for the whole fleet. That Prometheus scrapes the devices Mercury writes into its own targets
files, so a network with a Prometheus of its own is scraped by its own (see
[Settings](settings#network), the Prometheus card):

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

## Profile {#profile}

The network's profile: what every device inherits, its own value winning where it has one.

**A network with no profile of its own still gets monitoring.** If it inherits Default's
settings (see [Inherit or stand alone](settings-switch)), its devices take Default's profile,
and the page says so above the rows. That covers rendering, Coverage, a device's **Apply
monitoring profile…**, and onboarding's profile step at Verify. Propose gives it a profile of
its own, which then wins. A standalone network with no profile has none: Coverage says
"<network> has no monitoring profile yet, so nothing can be deployed: propose one from the
network's connectors first", and links to Propose here.

One row per committed section:

- **Derived from**: the connector or setting the section comes from (the SNMP exporter's
  community, never shown; the syslog receiver; the NTP servers; the interface syslog leaves
  from, for the management sources), or IP SLA's policy.
- **Applies to**: every device, or the platforms or roles the section is scoped to.
- **On the devices**: how many of the devices it applies to hold it, read from Coverage's
  cells, so the two pages agree. A device that lacks it is offered on Coverage, where
  **Deploy missing templates…** sends it. **Not rendered** means the device's template renders none of the section, so
  nothing can send it until the shipped template is brought in on Templates (see
  [Bring in a shipped template](bring-template)).

**Propose from the connectors…** opens the proposal below the table: each section new, changed,
as committed or not proposed with why, how many devices' committed intent it cross-checked and
each device it did not read with why, how many devices' effective intent changes, and which
of them would not receive a change yet because their template does not render it. Where the
devices hold different versions of a section's shared fields, it offers **Use the version held
by …** for each, and previews the one you choose with what every other device gains. Committing
it records the profile, and any version you chose, as you; nothing is sent to a device. See
[Apply a monitoring template](monitoring-templates#propose).

## Alerts {#alerts}

Every network's firing alerts, as Grafana's alert reader last stored them, each with its
**evidence pack**: what was gathered about its device when the alert began (see
[An alert's evidence pack](alert-evidence)). The line at the top counts them: how many are
firing, how many have their pack, how many are waiting for one, and how many packs belong to
alerts no longer firing.

The alerts are grouped by rule (a rule generated per device, such as a heartbeat, is one
group), each alert a closed card naming its device, its network, when it began and its onset,
how many pieces its pack holds and how many of its sources could not be read. A heartbeat or
telemetry alert whose device went silent fires as **Alerting (NoData)** and is listed here like
any firing alert, its pack saying what was absent (see
[When no data is the fault](alert-evidence#absence)). Open a card to
read its pack, section by section, each with its source, when it was read and the reference
the pack gave it. **Show** narrows the cards to a rule, device or label. **Earlier** holds the
packs of alerts that have resolved, the newest 50 drawn. A Needs attention row about an alert
opens its card here. An open pack's **Explain** carries the **AI** mark; when hosted AI cannot
answer it is disabled with the reason under it, and the pack is drawn whole (see
[The AI mark](installation-settings#ai-mark)). Its answer is kept with the pack: opening the
card again draws it, and nothing is sent; **Explain again** is a new call, said with its cost
(see [An answer is kept with its pack](alert-evidence#kept-answers)). Explain is advisory, in
beta: every answer, and the control itself, carries **Advisory (beta)**, the reliability
measured and "A person should confirm"; **How was this measured?** opens what was measured and
why it is still in beta (see [Advisory (beta)](alert-evidence#beta)).

The list redraws when the alert reader finishes a read, after any new pack is built, but never
under you: while a card you opened is open, or while Explain is being answered, it waits, and
the card says **Paused while you work** with **Show it now**. If the reader has not read
Grafana, or the pack record cannot be read, the tab says so instead of listing nothing.

{{product}}'s own SDN detections (a scan, a flood or an unauthorised flow on a controller's
switch) are listed here too, under their own source, **SDN detection**, with when it last judged;
if its state cannot be read, the tab says so and lists none of them. Their cards name the
**switch** (its DPID and controller connection) instead of a device, and their packs draw the
flows, ports and meters the detection rests on in words (see
[An SDN detection's pack](alert-evidence#sdn)).

The tab has two views, **Firing** (above) and **History**: the alerts that fired and resolved,
from {{product}}'s alert history, every time Grafana's own (see
[Alert history: past alerts and their evidence](alert-history)). History leads with a summary
(how many fired and resolved in the range, on how many devices, how many have a pack, and the
counts of those that only went pending, read no data or could not evaluate), then the filter
(words, rule, device, time, and **Fired** or **All**), then each rule as a closed group with its
count. A past alert with its pack opens it, with Explain; one without offers **Build evidence**,
which rebuilds its pack as of its time and marks each section captured, rebuilt or cannot be
rebuilt (see [Build evidence](alert-history#build)). Explain beside it stays disabled until the
pack is built.
