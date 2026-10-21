# Resource settings: every load Mercury puts on the network, adjustable in Settings

**Status:** design and sizing; build after Lab 8 (the operator, 2026-10-21). It comes from the
tuning sprint (C1485, docs/HOST_TUNING.md).

**The evidence:** polling is cheap for a router and heavy for a device that forwards management
traffic in software.
- On r2, IOSd as a whole was 5%; IP SLA took 0.83% and SNMP 0.24%.
- On s3, the vIOS switch that routes every router's management traffic to Mercury, IP SLA was
  its largest process at 12.7% (one probe every 10 s). Being polled by SNMP took 7.9%, and
  forwarding the routers' gRPC telemetry about 5%.
- Telemetry was 116 of the 200 packets a second s3 sent toward Mercury.
- So a load estimate that counts only the polled device is wrong. It must count every device the
  traffic crosses.

## 1. The rule

**Every resource-affecting setting Mercury owns is adjustable in Settings:**
- at three levels: an installation default, a per-network override and a per-device override;
- each value shown with where it comes from (inherited or set) and its load estimate.

**Dependent settings change together, or the change is refused naming the dependency.**
- **The heartbeat interval** decides each device's alert window and Grafana's rules. A change
  re-measures the windows and installs the rules in the same operation, or is refused, naming the
  rules that would go wrong.
- **The SNMP interval** decides the dashboards' rate windows and thresholds. A rate window must be
  at least four scrapes, so a change names each panel it breaks.
- **The telemetry interval** decides the telemetry rule's `last_over_time` window, which is three
  scrapes of the collector.

**Device-side intervals go through intent.** Changing the telemetry period, an IP SLA frequency or
the syslog heartbeat rewrites intent, then goes through the normal preview, confirm, deploy and
Verify. It is never sent around intent.

**Host-side intervals are Mercury's own** (its readers, jobs and timers) and take effect without a
device.

**Resource profiles set them all at once:** Minimum, Standard and Large. Each is a named set of
values with a load estimate for this network, so a person picks a profile and sees what it costs.

## 2. The settings

| Setting | Today | Where it lives | Device side? | Depends on it |
|---|---|---|---|---|
| Telemetry period (each subscription) | 10 s, in the profile's telemetry section (`update-policy periodic 1000`) | profile, by network | yes, through intent | the telemetry rules' window |
| IP SLA frequency | the policy: 60 s by network (`frequency`), by platform (`frequency_by_platform`) | profile, by network | yes, through intent | the IP SLA dashboard's panels |
| SNMP polling interval | Prometheus jobs: 30 s for the routers, 1 minute for the switches | the generated Prometheus config | no (Mercury's collector) | dashboard rate windows and thresholds |
| Syslog heartbeat interval | `syslog_heartbeat_seconds` 300, installation-wide | settings | yes, through intent (the applet) | heartbeat windows, Grafana rules |
| Drift interval | exists (`drift_interval`) | settings | no | none |
| Reader intervals | fixed in code per reader (`interval_seconds`, each with its measured basis) | code | no | each reader's promise and staleness |
| Job schedules (the hourly checks, NetBox's backups) | systemd timers | the host's units | no | none |
| Fleet-operation concurrency | `deploy_max_workers` 1, `reads_max_workers` 6 | settings | no | none |
| Heavy pages' parallel reads (C1483) | serial | code | no | none |

## 3. The gaps tonight showed

- **C1491: the IP SLA policy's frequency never reaches a probe that already exists.**
  - The network's policy says 60 s, and s2's probe follows it.
  - s3's probe (and two of r1's) still run at 10 s from before the policy. The policy skips a
    path "already measured" and sets the frequency only on the probes it creates.
  - Monitoring › IP SLA says "every 60 s" while s3 runs every 10 s.
  - **Changing s3 today needs a hand edit of its intent.** That is the Settings work's first
    piece, and why it is not done tonight.
- **No per-device override exists** for any of these, and no resource profile.
- **No load estimate counts transit devices.** `ip_sla_policy.cost_words` estimates a probe's cost
  on the probing device only.

## 4. The design

- **A "Resources" section in Settings:**
  - a table of the settings above, with the installation default, the network override and the
    device overrides (by device, collapsed for a large fleet);
  - each with its source (inherited or set) and an estimate.
- **Estimates from measurement, never guessed:**
  - each estimate names the device it was measured on and scales by frequency (as
    `cost_words` does);
  - it adds the transit cost on every device the traffic crosses, from the topology's path to
    Mercury.
  - For s3: forwarding cost per packet measured from "IOSv e1000" plus "IP Input" against its
    routed rate.
- **A change is one operation:** a preview listing every dependency it moves (rules, windows,
  panels, intent of N devices), a confirm by hash, and then:
  - the intent commits and the deploys (each through the pipeline, with Verify);
  - the Grafana rules re-measured and installed;
  - the Prometheus config regenerated.

  A dependency that cannot move with it refuses the change, naming it.
- **The IP SLA policy reaches existing probes:** its Apply proposes a frequency change for every
  probe whose frequency differs from its device's resolved value (the device override, then the
  platform's, then the network's), through intent, with preview and confirm.
- **Resource profiles:**
  - **Minimum:** telemetry 60 s, IP SLA 120 s, SNMP 2 minutes, heartbeat 600 s, drift 1 hour.
  - **Standard:** telemetry 30 s, IP SLA 60 s, SNMP 1 minute, heartbeat 300 s, drift 30 minutes.
  - **Large:** a fleet-size scaling of Standard.

  Each is shown with its estimate for this network, and picking one is a preview like any other
  change.
- **Host and hypervisor tuning stays out of Settings** (Mercury does not own the host). That
  covers the governor, C-states, NX huge pages, KSM, hugepages, NUMA binding and the vIOS tick
  policy. They go into the hardware guide per tier (docs/HOST_TUNING.md's proven changes), with an
  optional read-only Diagnostics check that reads what it can and says what it cannot.

## 5. Size

| Part | Size |
|---|---|
| The settings store with three levels and resolution (one resolver, C14's pattern) | M |
| The IP SLA policy reaching existing probes (C1491), with the per-device override | S to M |
| Telemetry period and heartbeat interval through intent, with their dependencies | M |
| SNMP interval: regenerate Prometheus jobs, check the dashboards' windows | M |
| Estimates with transit cost (measured per platform, the path from topology) | M |
| Resource profiles and the Settings section (a board, its fidelity record, the manual) | M |
| Reader intervals, job schedules, concurrency and parallel reads in Settings (C1483) | S to M |

**In all: L, about 6 to 8 days.** After Lab 8. C1491 is the first piece, because it is tonight's
largest lever on the device that stalls.
