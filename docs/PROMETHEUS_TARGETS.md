# Prometheus's SNMP targets, generated from the inventory (C232, C229)

## Why

Measured on the host, 2026-09-30, read-only:

- Prometheus's oldest sample is 2026-08-30T04:58:46Z (its install). Across all of
  it, no series has carried a `device` label naming a device, and no series has
  carried a `role` label at all. The only `device` values are node_exporter's
  disks and interfaces.
- `/etc/prometheus/prometheus.yml` and its four backups (`.bak`, 2026-09-07;
  `.bak-mdt`, 2026-09-07; `.bak-ipsla` and `.bak-lldp`, 2026-09-12) hold zero
  `device:` and zero `role:` labels, and no relabel rule writes either. The SNMP
  jobs list addresses by hand in `static_configs`, with the device names only in
  comments (`- 10.255.1.13 #r3`).
- So the labels were not lost from this Prometheus; it never had them. The
  `rcn-lab1-snmp` panels that select `device="$device"` have been empty in
  Grafana since the install, and the dashboard's `device` and `role` variables
  list nothing. When the scrape config that did carry them (Lab 2's) was
  replaced is not recoverable from this host.
- r6 (`10.255.0.32`) is in no SNMP job, and retired r5 (`10.255.1.15`) is still
  scraped by `cisco_8000v` and `lldp`, and still answers.

The fix is at the source: `scripts/nmas-prometheus-targets` generates the
targets from the inventory, each labelled `device` (its hostname) and `role`
(the inventory's). The dashboards then work as designed, r6 is scraped, and r5
stops being scraped.

## What is generated

`file_sd` files, one group per device (`targets: [address]`,
`labels: {device, role}`):

| File | Devices | For the job |
|---|---|---|
| `nmas-snmp-cisco_iosxe.json` | every `cisco_iosxe` device | `cisco_8000v` |
| `nmas-snmp-cisco_ios.json` | every `cisco_ios` device | `cisco_vios_l2` |
| `nmas-snmp-ipsla.json` | devices whose COMMITTED golden defines an `ip sla <n>` operation (measured: exactly the five `cisco_ipsla` lists today) | `cisco_ipsla` |
| `nmas-snmp-all.json` | every device | `lldp` |
| `nmas-snmp-ospf.json` | devices whose committed golden has `router ospf <n>` | `ospf` (to add, below) |
| `nmas-snmp-ospfv3.json` | IOS-XE devices whose golden has `ipv6 router ospf <n>` or `router ospfv3 <n>` (vIOS does not implement OSPFV3-MIB) | `ospfv3` (to add) |
| `nmas-snmp-bgp.json` | devices whose golden has `router bgp <AS>` | `bgp` (to add) |

**Only a device whose committed golden configures SNMP is a target** (the operator, 2026-09-30, C236): r6 was one with no SNMP in its configuration, and Grafana called it unreachable. Its absence is named in the run's notes, and job health's `monitoring:<device>` row says "r6 is not monitored by SNMP" until the monitoring profile (NSOT_PLAN P.9) gives it SNMP. A golden that cannot be read stops the generation, and the files stay as they were.

A device with no role in the inventory gets no `role` label, and the run says
so. The inventory today says `router` for the four switches and nothing for
r6; the targets carry that as it is (C225).

## The one-time install (a person's step on the Prometheus host)

1. Create the directory the NMAS writes into, owned by the NMAS service user:

   ```bash
   sudo install -d -o <user> -g <user> -m 0755 /etc/prometheus/nmas
   ```

2. From the checkout on the host, read the dry run, then write and show the result:

   ```bash
   scripts/nmas-prometheus-targets
   scripts/nmas-prometheus-targets --write /etc/prometheus/nmas
   ls -l /etc/prometheus/nmas
   ```

3. Keep a copy of the config:

   ```bash
   sudo cp -p /etc/prometheus/prometheus.yml /etc/prometheus/prometheus.yml.bak-nmas-targets
   ```

4. In each SNMP job, replace the whole `static_configs:` block with the file it
   reads. Leave `relabel_configs` as it is: its three rules touch
   `__param_target`, `instance` and `__address__` only, so the `device` and
   `role` labels pass through. For `cisco_8000v`:

   ```yaml
       file_sd_configs:
         - files: [/etc/prometheus/nmas/nmas-snmp-cisco_iosxe.json]
   ```

   and likewise `cisco_vios_l2` with `nmas-snmp-cisco_ios.json`, `cisco_ipsla`
   with `nmas-snmp-ipsla.json`, and `lldp` with `nmas-snmp-all.json`.

5. Check the config, reload, and confirm:

   ```bash
   promtool check config /etc/prometheus/prometheus.yml
   sudo systemctl reload prometheus
   scripts/nmas-prometheus-targets --check
   ```

   `--check` prints `MATCHES` when every SNMP job scrapes exactly the generated
   targets. It reads what Prometheus has LOADED as well as what it has
   discovered, so it tells three things apart (measured on the install,
   2026-09-30, when a check seconds after the reload blamed the config):
   `NOT LOADED` (the loaded config does not read the files: the edit, or its
   reload, did not take), `NOT YET DISCOVERED` (exit 3: inside one scrape
   interval of the reload or of a write, with the time to ask again), and
   `DIFFERS` (the same difference past that interval). Within a scrape
   interval (30 s), `rcn-lab1-snmp`'s `device` variable lists the devices.

6. Name the directory in Settings > Integrations > Prometheus, **Targets
   directory**: `/etc/prometheus/nmas`. From then on the NMAS writes the files
   itself.

## After the install

The NMAS regenerates the files whenever the inventory changes: every write
of a list's `devices.csv` (onboarding's promotion, adopt, retire, a role
edit, Add and Delete) and every NetBox inventory refresh wakes it, and a
backstop every 300 s catches a change made by another process (a CLI on the
host) and the IP SLA file, which follows the committed goldens. Prometheus
re-reads a changed `file_sd` file with no reload. Nobody runs a command.

Each run is recorded in `data/prometheus_targets_sync.json`, and job
health's `prometheus-targets` row is the check that it happened: it compares
the files on disk with what the inventory generates now, and Prometheus with
the files. A regeneration that failed is a row naming its error (usually the
directory's owner or mode, step 1); files behind a recent run read
`settling` with the time they will be current; files behind with no run for
longer than the backstop mean the keeper is not running. With no directory
named, nothing is written and the row's action is the Settings field.

## Uptime, routing adjacencies and telemetry (2026-09-30)

### Uptime: installed by the operator

`system` (the exporter's existing module, which walks sysUpTime) is added to the two
PLATFORM jobs only, `cisco_8000v` and `cisco_vios_l2`. Every device is in exactly one of
them, so each device reports uptime once; adding it to `cisco_ipsla` and `lldp` would give a
router three copies under three jobs.

**The switches' uptime is not trustworthy as a duration.** Read at install:
- the routers showed 187.4 h, matching the 2026-09-22 redeploy;
- the switches, redeployed at the same moment, showed 176.6 (s1), 176.4 (s2), 142.0 (s4)
  and 110.2 h (s3).

Measured afterwards, read-only, as sysUpTime's climb against real time (`deriv(sysUpTime[1h])
/ 100`), with no counter reset:

| Device | Rate |
|---|---|
| r1 to r4 | 0.996 to 1.004 |
| s1 | 0.94 |
| s2 | 0.94 |
| s4 | 0.77 |
| s3 | 0.60 |

These are the emulated timers' own rates (C9), not reboots. NTP corrects the time of day,
not the tick rate. So the device dashboard shows uptime only where the clock keeps real time
(rate at least 90%). Everywhere else it shows **reboots detected** (the counter's resets,
reliable however slowly it counts). The rate itself is the **device clock rate** panel, C9 as
a number for the first time.

### Routing adjacencies: built, the host steps are the operator's

The operator's staged run 5 (read-only `snmpwalk`, 2026-09-30) measured what each platform
answers:

| Device | OSPF-MIB | OSPFV3-MIB | BGP4-MIB | CISCO-BGP4-MIB `cbgpPeer2Table` |
|---|---|---|---|---|
| r3 (IOS-XE 17) | 6 neighbours | answers | 1 peer, IPv4 only | 2 peers (IPv4 and IPv6), both established |
| s3 (vIOS 15) | 5 neighbours (first two-way) | No Such Object | no BGP | no BGP |

**Built:**
- `deploy/snmp_exporter/generator.yml`, generated with `prom/snmp-generator:v0.29.0` (the
  exporter's own version) on the laptop, from the host's IETF MIBs and Cisco's CISCO-SMI
  and CISCO-BGP4-MIB.
- Its output, `deploy/snmp_exporter/routing-modules.yml`: `ospf` (the neighbour table, each
  neighbour labelled with its router id), `ospfv3` and `cisco_bgp_peer2`, with no auth
  section.
- The three target files above, from the goldens, written by the NMAS like the others.

**The operator's host steps:**

1. From the checkout, the dry run, then the append (a backup is kept, the append is
   proven, and nothing else in the file changes):

   ```bash
   scripts/nmas-snmp-add-modules
   sudo scripts/nmas-snmp-add-modules --apply
   docker exec snmp-exporter /bin/snmp_exporter --config.file=/etc/snmp_exporter/snmp.yml --dry-run
   docker restart snmp-exporter
   ```

2. Three jobs in `prometheus.yml`, each shaped like `cisco_ipsla` (the same `auth:
   [public_v2]` and the same three relabel rules, with its own module and file):

   ```yaml
     - job_name: ospf
       metrics_path: /snmp
       params: {auth: [public_v2], module: [ospf]}
       file_sd_configs:
         - files: [/etc/prometheus/nmas/nmas-snmp-ospf.json]
       relabel_configs: <the same three rules as cisco_ipsla>
     - job_name: ospfv3        # module [ospfv3], file nmas-snmp-ospfv3.json
     - job_name: bgp           # module [cisco_bgp_peer2], file nmas-snmp-bgp.json
   ```

   Then run `promtool check config /etc/prometheus/prometheus.yml`, reload, and
   `scripts/nmas-prometheus-targets --check`.

**Two-way is not a fault.** Two routers that are neither DR nor BDR stay at two-way by design
(s3 shows it). So the dashboard counts only the genuinely wrong states: down, attempt, init,
and stuck in exstart, exchange or loading, plus a BGP peer that is configured up and not
established. It draws each neighbour's state, with two-way in neutral text.

### Telemetry: the label fix is the operator's host step

The `telemetry_mdt` series name the device `source`, not `device`. The cleanest fix is one
rule on that job in `prometheus.yml`, which COPIES `source` into `device` (so `source` keeps
working), and every panel then selects a device one way:

```yaml
  - job_name: telemetry_mdt
    ...
    metric_relabel_configs:
      - source_labels: [source]
        regex: '(.+)'
        target_label: device
        replacement: '$1'
```

It touches only series that HAVE a `source` (the Cisco ones). Telegraf's own host metrics
(`diskio_*`, whose `device` is a disk name) have none, so they are left alone. The Telegraf
equivalent (a `[[processors.rename]]` of the tag) would do it at the source, but it is a
second config to own; the relabel sits beside the other scrape edits.

**Resolution:** the routers push every 10 s (`update-policy periodic 1000`), but Prometheus
scrapes Telegraf every 30 s, the same as SNMP. `scrape_interval: 10s` on `telemetry_mdt`
alone would keep what the devices send.

**CPU is two measurements, not one from two collectors** (measured 2026-09-30, read-only):

| Router | Telemetry, 1 min | SNMP `cpmCPUTotal1minRev` | Telemetry, 5 min | SNMP, 5 min |
|---|---|---|---|---|
| r1 | 8 | 54 | 14 | 66 |
| r2 | 9 | 52 | 14 | 63 |
| r3 | 11 | 55 | 15 | 62 |
| r4 | 8 | 54 | 15 | 64 |

The telemetry model's figure is most likely the IOS processes' (`show processes cpu`) and
SNMP's the whole route processor (`show processes cpu platform`). That attribution is not
measured; one router's two commands settle it. So the dashboard never merges them:
- the glance value is SNMP's on every device, so it means the same thing on every platform;
- CPU over time draws both lines, each named.

Traffic, errors and discards are the same counters from either collector, so telemetry is
primary there and SNMP the fallback, per device, with the source named on every series.

## What it does not do

- It does not touch alert rules (P.7).
- Series from before the switch-over keep their old labels until retention
  (90 days) removes them. A panel selecting `device` shows data from the
  switch-over on.
- A device is scraped only once its committed golden configures SNMP, and then
  only answers if its community is the one the job's `auth` module speaks.
