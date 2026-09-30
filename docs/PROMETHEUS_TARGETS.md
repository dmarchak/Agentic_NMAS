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

## What it does not do

- It does not touch alert rules (P.7).
- Series from before the switch-over keep their old labels until retention
  (90 days) removes them. A panel selecting `device` shows data from the
  switch-over on.
- A device is scraped only if it answers SNMP with the job's `auth` module. r6's
  scrape reads `down` until its SNMP configuration matches the others'; the
  target being present is what makes that visible.
