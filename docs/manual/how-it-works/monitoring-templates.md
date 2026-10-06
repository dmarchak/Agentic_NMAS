# Apply a monitoring template

Monitoring is configured the same way on every device by the network's monitoring profile:
one committed document with a section each for SNMP, syslog (the heartbeat is part of it),
NTP, LLDP, CDP, telemetry and IP SLA. Each section is derived from the monitoring tools
themselves (the connectors in Settings), and each device inherits it, its own value winning
where it has one. Applying the profile sends a device the profile's lines it lacks, and
nothing else.

![Applying the monitoring profile: Coverage reads each device's committed golden; the preview plans each ticked device's profile-only program from its stored capture and sends nothing; one confirm starts a batch that deploys one device after another, each through the deploy pipeline, and records one golden commit and a receipt per device.](diagrams/monitoring-templates.svg)

## Where you see it

Monitoring > Coverage shows every device against five integrations: SNMP, syslog, the
heartbeat, telemetry and IP SLA, each read from the device's committed golden (never from the
device). A cell reads configured; missing, saying whether the profile supplies it; excluded
by the device's intent, with the reason; not applicable, with why (the profile scopes the
section to other platforms or roles); not used, when the network has no connector for it;
or unknown, when the golden cannot be read. NTP, LLDP and CDP are profile sections with no
Coverage column. A device is ticked for Apply only when the profile supplies one of its
gaps; any other device says why beside its box.

The profile itself is made by **Propose** (on today's page, opened from Coverage's notice or
from Needs attention when there is none): the tool derives each section from the connector
settings, cross-checks the fleet's committed intent and names any device configured
differently, and commits the profile as you, `Source: profile`, once you confirm its hash.
Nothing is sent to a device by proposing.

## What Apply does

Apply is a deploy scoped to the profile's lines (see [Deploy a change](deploy)):

1. **Choose the devices.** On Coverage, tick devices and press **Preview applying the
   profile…**. Read: nothing yet. Sent: nothing. Recorded: nothing. The ticked devices travel
   in the page's address to the preview.
2. **The preview.** Read: each device's committed golden (the capture the plan computes
   against), its committed intent and the committed profile. Sent: nothing; no device is
   contacted. Recorded: nothing. Each device's plan is the deploy plan with scope `profile`:
   the lines it would send (masked), the profile's lines already in place, the device's own
   intent changes held back (never sent by this action), and each OLD monitoring line the
   profile supersedes, with a box to remove it (Mode B) and a field for its reason. A device
   with nothing to send leaves the order. A preview can be re-planned with a device moved
   **Earlier** or **Later**, or **Left out**.
3. **Confirm.** Read: nothing. Sent: nothing yet. Recorded: nothing yet. The confirm carries
   each device's capture and program hashes in the order shown, and the removals with their
   reasons. The server answers at once and starts the batch as a job, as you.
4. **The batch.** Read, Sent and Recorded: as each device's pipeline below. One device after
   another, in your order, each program computed again at apply and refused alone, with
   nothing sent to it, if its hash moved. The page shows each device done, running or not
   reached as the job announces it over the live channel, then the result from the
   receipts. Sequential on purpose: a bad change stops after the first device it breaks.

Each device runs the deploy's pipeline, its stages in the order the code declares them:

1. **NetBox context** (`netbox_query`). Read: the device's NetBox record, if NetBox is
   configured. Sent: nothing. Recorded: nothing.
2. **The confirmed program** (`template_render`). Read: nothing. Sent: nothing. Recorded:
   nothing. The program you confirmed is used as it is; nothing is rendered again here.
3. **Dangerous lines** (`ci_gate`). Read: the program. Sent: nothing; no session is open
   yet. Recorded: nothing. A dangerous line, or a ticked removal, must carry the reason you
   gave.
4. **Before** (`pre_snapshot`). Read: over SSH, the running configuration (kept for a
   rollback), routing neighbours, routes and interfaces. Sent: only show commands.
   Recorded: nothing yet.
5. **Something to send** (`config_diff`). Read: the program against that read. Sent:
   nothing. Recorded: nothing. A device that already holds every line is refused here.
6. **Send** (`deploy`). Read: the device's replies. Sent: the profile's lines, in
   configuration mode, merge-only, then any removal you ticked. Recorded: the time of the
   push, which verify's BGP watch counts from.
7. **After** (`post_snapshot`). Read: the same facts, on a new SSH session. Sent: only
   show commands. Recorded: nothing yet.
8. **Verify** (`verify`). Read: the two snapshots and the new lines read back. Sent:
   nothing, unless verify fails and the rollback sends the undo. Recorded: the verdict. A
   program that touches only management sections (logging, SNMP, NTP, users, terminal
   lines, banners) gets the quick verify: each new line read back, no wait for BGP's hold
   time. LLDP, CDP, telemetry or the heartbeat's applet get the full one.
9. **Save** (`save_startup`). Sent: `write memory`, only once verify passed. Recorded: whether
   it saved.
10. **The golden** (`save_golden`). Read: the configuration after the change. Sent: nothing.
   Recorded: the batch's captures as ONE golden commit, as you, after the last device.
11. **The record** (`audit_log`). Read: nothing. Sent: nothing. Recorded: the run's audit
    file, whatever happened; and, after the commit, a receipt per device (what was sent, the
    checks that ran, any rollback), shown on the device page's History tab.

## Deploy missing templates {#combined}

Coverage's **Deploy missing templates…** sends each ticked device ONE program: every template
it is missing, the profile's lines and the IP SLA probes committed to its intent, sent,
verified and rolled back as one. Nothing else in its intent is sent, and nothing on a device
is removed. It is the deploy above with scope `templates`:

1. **Choose the devices.** On Coverage, tick devices (a box is drawn only where something can
   be deployed) and press **Deploy missing templates…**. Read: nothing yet. Sent: nothing.
   Recorded: nothing.
2. **The preview.** Read: each device's committed golden, its committed intent, the
   committed profile, and Coverage's stored reading of which templates are missing and which
   are configured and not reporting. Sent: nothing; no device is contacted. Recorded:
   nothing. A card per device in the order they will go: the templates its program holds, the
   program itself (the first device's open, the others one click down), its checks, with the
   operands they compared on hover, and each template that is configured but not reporting,
   named with **Diagnose it**. A template not reporting is never part of the deploy: its
   lines are already on the device, and the cause is looked for on the device's page.
   **Earlier**, **Later** and **Leave out** plan the deploy again.
3. **Confirm.** Read: nothing. Sent: nothing yet. Recorded: nothing yet. The confirm is bound
   to the programs on the screen: if a device or a template changed since, that device is
   refused, with nothing sent to it, naming what moved. The server answers at once and starts
   the deploy as a job, as you.
4. **The deploy.** As the batch above, one device after another in your order, each through
   the deploy's pipeline, then one golden commit and a receipt per device, with two
   differences:
   - **Verify reads every line it sent back,** quick or full. A line the device does not show
     fails verify, and the device's whole program is rolled back: one change, rolled back as
     one, never a device left with part of its templates.
   - **The first device that fails stops the rest,** whatever failed: its push, its verify,
     or a program that moved since the preview. The devices after it are not attempted, and
     the result says so. (Other deploys stop after repeated verify failures.)
5. **The arrival watch.** Read: Coverage's stored reading, each minute (it reads Prometheus
   and Loki itself; the watch asks nothing of its own). Sent: nothing. Recorded: nothing; the
   watch is in memory with the job. For 15 minutes after the batch, each template a deployed
   device was sent is watched for its first data: SNMP's and IP SLA's first scrape, the first
   syslog line, the first heartbeat, telemetry's first series. The result shows each as it
   arrives, with its time and how many seconds after the batch, and anything still missing
   at 15 minutes says so, with a link to the device tab where its cause is looked for. NTP and
   LLDP are device state, not an arrival, and are said as not read. It never blocks and never
   rolls back: the configuration that read back stays. The 15 minutes is about 2.5 times the
   slowest expected arrival (a 5-minute heartbeat and a 1-minute reading); the first real
   deploy's arrival times are its measurement.

### Why arrival is watched after the batch {#arrival}

Waiting for each device's data inside its verify would add 5 to 6 minutes to every device
(the heartbeat fires every 5 minutes, and the reading is taken once a minute), and could
never see SNMP: a device's scrape target is created when the batch's golden commit
regenerates the targets, after the last device. So the batch deploys and verifies what it
sent, and arrival is watched afterwards, as a report, not a gate.

## The heartbeat

Each device runs an applet that logs a heartbeat line on a timer (the profile's syslog
section sets the interval, from the syslog connector's heartbeat seconds), sent by syslog
to the log store (Loki). A Grafana alert
rule per device, with a window measured from that device's own arrivals, fires when the
heartbeat stops; the tool reads Grafana's alerts every minute and the stopped heartbeat is a
Needs attention row. An hourly check on the host (`nmas-heartbeat-check`, a systemd timer)
re-measures each window; when a device's rate has moved, job health raises a row whose
action opens the re-measure, which writes new rules as you and names the one host step that
installs them in Grafana. That host step is still a person's: an automatic re-measure and
install is decided, and not built.

## Changing (awaiting the operator's sign-off, 2026-10-02) {#changing}

Each section becomes a template with its own settings (Settings > Monitoring templates),
Coverage's cells each offer Deploy for one template, and IP SLA's probes are generated by its
template and committed with it in one commit. This page is rewritten when that is built.

## Save a template's settings {#save}

Nothing saves a template's settings yet: there is no Settings > Monitoring templates page,
and no template exists apart from the profile's sections. Two saves exist today that come
closest:

1. **The connectors** (Settings > Integrations > Monitoring profile). Read: nothing. Sent:
   nothing. Recorded: the syslog settings (host, trap level, origin id, source interface,
   heartbeat seconds), snmp_exporter's file and auth module, the trap host, Telegraf's
   listener and the NTP servers, in the app's settings, validated. Nothing is committed: the
   next Propose derives the profile from them. **Test** checks what can be checked.
2. **IP SLA's policy** (Monitoring > IP SLA, reached from Coverage's IP SLA cells). Read: the
   committed profile. Sent: nothing. Recorded: the profile's IP SLA section (its targeting,
   routing peers or the default gateway or none, and its frequency, 10 to 3600 s) committed
   as you, `Source: profile`, refused if the profile moved since the page showed it. The
   probes it suggests are a SECOND commit, into the chosen devices' intent
   (`Source: ip-sla`), and are sent by Coverage's [Deploy missing templates](#combined) or by
   a scoped Apply (scope `ip_sla`), never by the profile's Apply.

The signed-off design (not built) says: each template's settings live with it in Settings >
Monitoring templates, one compact row each; IP SLA's are its targeting, its frequency and its
CPU note. Saving a template commits it and the per-device lines it generates (IP SLA's probes,
in each device's intent) as ONE commit. Nothing is sent until a deploy.
