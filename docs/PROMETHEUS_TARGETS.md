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

**When the files are rewritten** (the operator, 2026-09-30: r6's new golden gave it
SNMP, and only the 300 s backstop caught it). Every group a device belongs to is
read from its COMMITTED golden, so the keeper is woken by:
- an inventory write (Add, Delete, a role edit, onboarding's promotion, adopt,
  retire, a NetBox refresh);
- **a commit that changes a golden**, through the list repository's post-commit
  hook (`prometheus-targets`), which every commit reaches by construction (C223):
  a deploy, a capture, Save All, a restore. One owner decides eligibility
  (`generate()`); the hook only wakes it, and only files whose content moved are
  written;
- the 300 s backstop, for a change another process made.

**What joins a group, and what does not.**
- A device joins `ospf`, `ospfv3` (IOS-XE only), `bgp` or `ipsla` when its
  committed golden gains the protocol, and leaves when it loses it; each round
  trip is a test on a real golden (`TestTheRoutingGroupsRoundTrip`).
- **A change made by hand on a device joins only once it is captured.** Until a
  capture commits it, it is drift, drawn as drift, and no target follows it.
- **A protocol with no group is not covered**: RIP (s1 and r1 run it today),
  EIGRP and IS-IS each need a generated snmp_exporter module, a job and a group
  before any of their adjacencies are scraped.

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

2. Three jobs in `prometheus.yml`. **Made by COPYING the `cisco_ipsla` job** (the operator,
   2026-09-30): the same timing, auth and relabel rules, changing only the name, the module and
   the file. Copying, rather than writing a job from the sketch below, keeps the settings that
   already work identical:

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

### Telemetry: the label fix, installed by the operator

**Installed 2026-09-30:** ospf 6 targets up, ospfv3 4 and bgp 2; the telemetry series carry
`device` r1 to r4; and `--check` reads MATCHES for 7 jobs.

The `telemetry_mdt` series named the device `source`, not `device`. The rule installed on that
job fills `device` from `source` ONLY WHERE `device` IS ABSENT, so every panel selects a device
one way and nothing that already has a `device` is overwritten:

```yaml
  - job_name: telemetry_mdt
    ...
    metric_relabel_configs:
      - source_labels: [device, source]
        separator: ';'
        regex: ';(.+)'
        target_label: device
        replacement: '$1'
```

The joined value is `<device>;<source>`, and `;(.+)` matches only when `device` is empty.
Telegraf's own host metrics (`diskio_*`, whose `device` is a disk name) keep their `device`,
and a Cisco series keeps `source` beside the new `device`. The Telegraf
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

**Measured on r3 by the operator, 2026-09-30:**
- `show processes cpu` read 2/6/15% (5 s, 1 min, 5 min): IOS's own CPU, which matches
  telemetry's 8 to 11%.
- `show processes cpu platform` read 40/41/70%, with `ucode_pkt_PQF0` alone at 90/91/93%. That
  is the virtual router's packet-forwarding engine, which busy-polls whether or not packets
  arrive, and it is what holds SNMP's `cpmCPUTotal` at 52 to 55% on every router, idle or not.

So at a glance the dashboard shows **IOS CPU**, IOS's control-plane CPU and the figure that says
a router is under strain: from telemetry on IOS-XE, and from SNMP's `cpuAvgBusy1` on vIOS,
which is already IOS's own (nothing polls there). Both carry the same label, so the two compare.
The platform figure is one level down, with a note that a high flat line is normal on a
virtual router.

**Memory:** vIOS implements none of the modern memory tables (measured by the operator on s3:
CISCO-MEMORY-POOL-MIB and CISCO-PROCESS-MIB's `cpmCPUMemoryUsed` are all No Such Object; r3
answers all three). So on a vIOS device the memory panel says "Memory isn't available over
SNMP on vIOS", never an empty chart, until staged run 6 measures the old family's `freeMem`.
On the routers the memory figure is SNMP's: no telemetry memory subscription exists yet (the
monitoring profile's telemetry section is where one would be added).

Traffic, errors and discards are the same counters from either collector, so telemetry is
primary there and SNMP the fallback, per device, with the source named on every series.

## What it does not do

- It does not touch alert rules (P.7).
- Series from before the switch-over keep their old labels until retention
  (90 days) removes them. A panel selecting `device` shows data from the
  switch-over on.
- A device is scraped only once its committed golden configures SNMP, and then
  only answers if its community is the one the job's `auth` module speaks.
