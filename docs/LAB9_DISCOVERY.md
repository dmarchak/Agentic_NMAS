# Lab 9: reading switches Mercury has no driver for

**For the Lab 9 sitting (2026-11-05), on the laptop installation** (docs/LAB9_SDN_GAP.md 2.4):
its own data directory, NetBox in Docker, the network `lab9` taking its devices from NetBox, no
git remote. The main session merges this into docs/LAB9_LAPTOP_RUN.md.

The lab's two Arista switches and one HP switch are of models not known before the sitting.
Mercury has no driver for either vendor (docs/LAB9_SDN_GAP.md 2.1). This page describes how they
are **read, and nothing else**. Their answers are the input to the driver build.

## 1. What Mercury does with these switches

A platform with no driver gets a **discovery driver**, which is netmiko's own type for it
(`modules/discovery.py`):

| Discovery driver | Netmiko class (4.3.0, locked) | Family | Paging turned off by the driver, before the first command |
|---|---|---|---|
| `arista_eos` | `AristaSSH` | Arista EOS | `terminal length 0` (and `terminal width 511`) |
| `hp_procurve`, `aruba_osswitch`, `aruba_procurve` | `HPProcurveSSH` | HP ProCurve / ArubaOS-Switch | `enable`, then `terminal width 511` and `no page` |
| `aruba_os` | `ArubaSSH` (netmiko: "For use with Aruba OS Controllers") | Aruba; given AOS-CX's list | `enable`, then `no paging` |
| `hp_comware` | `HPComwareSSH` | HP Comware (Comware 7: an HPE 5130, 5900 or the like) | `screen-length disable`; `enable` is never sent (below) |
| `ovs_linux` | `OvsLinuxSSH` (`LinuxSSH` with nothing added) | Open vSwitch on a Linux server | none needed; `enable` (`sudo -s`, a root shell) is never sent. Its one write is the OpenFlow configuration's transaction, while held (docs/LAB9_OPENFLOW.md) |

No command needs an answer to a pager.

**Comware's `enable` is configuration mode.** In netmiko 4.3.0, `HPComwareBase.enable` enters
`system-view`. So on a Comware session `enable` sends nothing, and the reads run in user view.
Every configuration-mode call stays refused.

**`display` is a read only on a Comware session (C2530).** The read-only allowlist has no
`display` verb, and no other capture list has one.
- Ask the device and Show commands accept a Comware `display` read for a Comware device. They
  refuse it for any other device before a session opens, naming the command, the family and the
  device's driver.
- An IOS session refuses it too, held or not. So a held IOS read never sends it.

**What such a device may do (a positive allowlist):**
- It is read by its family's capture list (section 3), one command at a time, each command
  whole. A spacing or case difference is the same command. Anything else is refused before a
  session opens, naming the command: on **Ask the device** and **Show commands**, and on every
  other path at the session itself (`connection.DiscoveryOnly`).
- **No config, save or commit call reaches it, held or not.** A deploy, a save (Persist, Save
  All), a restore, a credential rotation, a Reload and a privileged command are each refused at
  the session, naming the driver and the call.
- Above the session, everything that parses, renders, records a golden or deploys refuses the
  device already. A discovery driver has no config dialect, so its platform is unknown
  (`platform.require_platform`).
- **Every answer is masked twice:** first by `redact_text`, then line by line
  (`discovery.mask_lines`), because `redact_text`'s rules are IOS's. Measured 2026-11-05:
  - EOS's `username … role … secret sha512 <hash>` passed `redact_text` whole, and so did
    AOS-CX's `password ciphertext`;
  - ProCurve's `password manager … sha1 "<hash>"` kept its hash.

  So the rest of any line holding a credential word is masked (`<redacted:discovery>`), and the
  line's first words stay readable.

## 2. The steps in Mercury

1. **Create the NetBox record (a gap).** Mercury can't create a NetBox record for a platform it
   has no driver for. Devices › Add device… and Adopt a device… each need a config dialect.
   - So each switch's record is made in NetBox's own interface. That is break-glass, and the
     gap is a proposed row.
   - Each record needs a site, a Device Role whose `mercury_kind` is `switch`, a device type,
     a platform (a slug such as `arista-eos`, `aruba-os-switch` or `aruba-cx`) and a
     **primary IPv4 address**.
   - A device with only an IPv6 management address is skipped by the import (`primary_ip4`
     only, a break site under C1245). Its reads work over IPv6 once it is in.
2. **Give the switches a login.** On **Credentials › Profiles**, use **Add a profile…** with a
   `role:` or `site:` profile that covers the switches. A NetBox device carries no login of its
   own.
   - Give the enable secret only if the switch asks for one. The HP's `enable` sends the
     profile's username and then the enable secret, or the password when no secret is set.
3. **Map each platform.** On **Settings › Installation › Platforms and roles**, add a row to
   the platform map:
   - the NetBox platform's slug;
   - its **Driver**: `arista_eos` for the Arista, `hp_procurve` for a ProCurve or
     ArubaOS-Switch, `aruba_os` for an AOS-CX (section 3.3), `hp_comware` for a Comware
     switch (section 3.4);
   - **Config dialect**: *none: read only (a discovery driver)*;
   - **Delivers by**: ssh.

   Press **Preview changes**. It names the devices the row loads. **Test with** one of them
   reads `show version` through that driver (`display version` for Comware); then press
   **Save**. The row then says it is read
   only. A discovery driver with a dialect is refused.
4. **The first contact keeps the switch's SSH host key**, and every later session checks it.
   A changed key is refused, naming both.
5. **Read.** Use **Show commands** (the sidebar):
   - pick the vendor's switches by name;
   - enter the family's capture list from section 3, at most 10 commands;
   - press **Save the set**, so the list is committed to `lab9`'s repository, then **Run**.

   The result page shows each command on each switch, masked. One command on one switch is
   **Ask the device** on its device page. Each answer is kept to the network's **Show commands:
   answer cap (KiB)** (Settings, the network's tab; 32 KiB), and a longer one says it was cut.
   Raise the cap before reading a large `show running-config`.

## 3. The capture lists

A command is **confirmed** when one of these names it:
- netmiko 4.3.0's own source (its autodetect table: `show version` for `arista_eos` and
  `hp_procurve`, `display version` for `hp_comware`);
- ntc-templates 3.5.0's index (in CI's environment), which parses it for that platform;
- a vendor command reference cited here, with the date it was read.

Everything else is **(inferred)**, from vendor command-line conventions or a source that is not
the vendor's, and is to be checked on the switch. Each list's **ZTP or auto-configuration
status** read is the last row.

### 3.1 Arista EOS (`arista_eos`)

| Command | Source |
|---|---|
| `show version` | confirmed (netmiko autodetect; ntc-templates) |
| `show running-config` | (inferred) |
| `show interfaces status` | confirmed (ntc-templates) |
| `show ip interface brief` | confirmed (ntc-templates) |
| `show lldp neighbors` | confirmed (ntc-templates) |
| `show openflow` | (inferred) |
| `show openflow flows` | (inferred) |
| `show openflow ports` | (inferred) |
| `show zerotouch` | (inferred). Arista's EOS 4.37.0F manual ("Initial Switch Access", read 2026-11-05) names only `zerotouch cancel`. DISA's STIG for Arista MLS EOS 4.x (V-256029) runs `sh zerotouch` and reads its `Zerotouch Mode:` line |

`| json` is refused, as every output modifier but the filters is.

### 3.2 HP ProCurve and ArubaOS-Switch (`hp_procurve`, `aruba_osswitch`, `aruba_procurve`)

| Command | Source |
|---|---|
| `show version` | confirmed (netmiko autodetect) |
| `show system` | confirmed (ntc-templates) |
| `show running-config` | (inferred) |
| `show interfaces brief` | confirmed (ntc-templates) |
| `show vlans` | confirmed (ntc-templates) |
| `show lldp info remote-device` | confirmed (ntc-templates) |
| `show openflow` | (inferred) |
| `show openflow instance <name>` | (inferred); the name is one token, letters, digits, `_` and `-`, at most 32 |
| `show dhcp client vendor-specific` | (inferred). An HPE Aruba community answer shows it giving the DHCP vendor class and whether vendor-specific processing is enabled; no HPE command reference was found for it (2026-11-05). `show autorun` was not found in any source and is not on the list |

ArubaOS-Switch's DHCP auto-configuration is `dhcp config-file-update`, enabled by default (the
ProCurve management guides, read 2026-11-05). Being the default, it does not appear in
`show running-config`.

### 3.3 AOS-CX (driver `aruba_os` today)

The locked netmiko 4.3.0 has no `aruba_aoscx`. netmiko 4.6.0 has it, as the laptop's system
Python does, and its session preparation sends `no page` (read in 4.6.0's
`aruba/aruba_aoscx.py`). The lock is not changed here: that is LAB9_SDN_GAP decision 6.

`aruba_os` is netmiko's ArubaOS controller driver. It sends `no paging` to turn paging off, and
whether AOS-CX accepts that is **unknown**. If it does not, a long answer stops at a pager
prompt and is reported as failed when the read times out. **Read `show version` first.** If a
long answer fails, the HP needs the lock change.

| Command | Source |
|---|---|
| `show version` | (inferred) |
| `show system` | confirmed (ntc-templates, `aruba_aoscx`) |
| `show running-config` | (inferred) |
| `show interface brief` | (inferred; ntc-templates parses `show interface`) |
| `show vlan` | (inferred) |
| `show lldp neighbors-info` | (inferred, from ntc-templates' `show lldp neighbors-info detail`; the brief's `neighbor-info` is not AOS-CX's spelling) |
| `show openflow` | (inferred) |
| `show ztp information` | confirmed: HPE AOS-CX 10.03 and 10.06 command references, "show ztp information" (support.hpe.com, read 2026-11-05); operator or manager context |

### 3.4 HP Comware (`hp_comware`)

| Command | Source |
|---|---|
| `display version` | confirmed (netmiko autodetect: "HPE Comware", "HP Comware") |
| `display device manuinfo` | confirmed (ntc-templates) |
| `display current-configuration` | (inferred) |
| `display interface brief` | (inferred; ntc-templates parses `display interface`) |
| `display vlan brief` | confirmed (ntc-templates) |
| `display lldp neighbor-information list` | confirmed (ntc-templates) |
| `display openflow summary` | confirmed: H3C S5130-HI OpenFlow Command Reference, Release 1312-6W101 (Comware 7; read 2026-11-05) |
| `display openflow instance` | confirmed: the same reference |
| `display openflow instance <id>`, with `controller`, `listened` or `flow-table` after it | confirmed: the same reference; the id is one number, 1 to 4 digits |

**Comware's ZTP status has no read on the list.** Comware 7's automatic configuration is
`autodeploy` (the H3C Comware 7 Fundamentals Command Reference: `autodeploy sms enable`,
`autodeploy udisk enable`, `autodeploy url enable`). None of the sources read on 2026-11-05
names a `display` command for its state, so `display autodeploy` is not on the list.
`display current-configuration` should show an `undo autodeploy` line for any method turned off
(inferred: a non-default setting is shown).

The H3C reference is for H3C-branded Comware 7. The HPE-branded 5130's reference was not
found, so each command is to be checked on the switch.

### 3.5 Open vSwitch (`ovs_linux`)

Each command runs under `sudo -n`, which never prompts. The server's sudoers grants the login
`ovs-vsctl` and `ovs-ofctl` with no password, or sudo refuses in its own words and nothing runs.
`<bridge>` is one Linux interface name of at most 15 characters.

| Command | Source |
|---|---|
| `ovs-vsctl --version` | (inferred: Open vSwitch's common option, not quoted from ovs-vsctl(8)) |
| `sudo -n ovs-vsctl show`, `list-br` | confirmed: ovs-vsctl(8), Open vSwitch 4.0.0 (read 2026-11-05) |
| `sudo -n ovs-vsctl --columns=target,is_connected list controller` | confirmed: the same page (`list` with `--columns`) |
| `sudo -n ovs-vsctl get-controller <bridge>`, `get-fail-mode <bridge>`, `list-ports <bridge>` | confirmed: the same page |
| `sudo -n ovs-vsctl get bridge <bridge> protocols`, `get bridge <bridge> datapath_id`, `--if-exists get bridge <bridge> other-config:datapath-id` | confirmed: the same page (`get`), and the columns from ovs-vswitchd.conf.db(5); `--if-exists` with `get` (inferred) |
| `sudo -n ovs-ofctl -O OpenFlow13 show <bridge>` | (inferred; ovs-ofctl(8) was not read) |

## 4. What to read in each answer to pick the driver

- **The model:**
  - EOS: `show version`'s first lines (`DCS-7050…` or the like);
  - ProCurve: `show system`'s product line, and the product number in `show version` or in the
    first line of `show running-config` (`; J9727A Configuration Editor`, inferred);
  - AOS-CX: `show system`'s product name.
- **The OS family and release:**
  - EOS: `Software image version`;
  - ProCurve and ArubaOS-Switch: `show version`'s `Image stamp` path, whose release code
    names the family (`WB.16.…` and the like, inferred);
  - AOS-CX: `show version`'s `Version` line (`FL.10.…` and the like, inferred).

  The family decides the driver: EOS; ArubaOS-Switch, which is the ProCurve driver; AOS-CX,
  which is the lock change; or Comware (`display version`'s `Comware Software, Version 7.…`
  line, inferred).
- **The OpenFlow version and mode:** in `show openflow`, and on ProCurve
  `show openflow instance <name>`:
  - whether OpenFlow is enabled, and its version (1.0 or 1.3);
  - on ProCurve, each instance's member VLAN, which is how "OpenFlow on the right ports" is
    expressed there (inferred);
  - on EOS, the bind mode and its bound interfaces or VLANs;
  - the fail mode (secure or standalone).

  A switch that speaks 1.0 only changes Mercury's flow writes (docs/LAB9_SDN_GAP.md 2.1, the
  hardware risk).
- **The controller connection fields:** each controller's address, port (6633 or 6653) and
  transport (tcp or ssl), and whether it is connected now. These become the OpenFlow intent
  section's fields (LAB9_SDN_GAP item 2).
- **The management network:**
  - `show ip interface brief`, `show interfaces brief` or `show interface brief`, with
    `show vlans` or `show vlan`;
  - `show lldp …`, which says what each port faces.

- **The ZTP status:** whether the switch is still in zero-touch or auto-configuration mode, and
  what it last fetched (section 3's last row for each family). This decides which vendor ZTP
  profile applies.

## 5. The captures

Every answer a discovery device gives is a **capture**: the input for confirming a vendor
OpenFlow template.

- The store is the reads engine's own record: one file per run, each device's answers masked,
  with the time and the SHA-256 of each. Nothing new writes it. The record now also says which
  discovery driver read each device.
- A capture is named `<device>/<command>/<run id>`. The command's words are joined by `_`, so
  `sw1/show_running-config/20261105T…Z-…`. The run id is its start in UTC
  (`discovery.captures`, `discovery.capture`).
- A capture is kept as the reads engine keeps every answer: for the network's **Show commands:
  answers kept (days)**, then moved to its archive, never deleted. On the laptop no archive is
  configured, so the answers stay.
- A Cisco device's reads are not captures.

## 6. What this does not do

- It has no driver: no deploy, verify, golden or drift.
- It creates no NetBox record: step 1 is a gap.
- It doesn't read Comware's ZTP state with a command of its own (section 3.4).
- It doesn't change the netmiko lock for AOS-CX.
- Its masking cases are line shapes, not captures. A real capture's lines replace them after
  the sitting.
