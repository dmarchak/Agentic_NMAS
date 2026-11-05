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

No command needs an answer to a pager.

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
     ArubaOS-Switch, `aruba_os` for an AOS-CX (section 3.3);
   - **Config dialect**: *none: read only (a discovery driver)*;
   - **Delivers by**: ssh.

   Press **Preview changes**. It names the devices the row loads. **Test with** one of them
   reads `show version` through that driver; then press **Save**. The row then says it is read
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

A command is **confirmed** when netmiko 4.3.0's own source names it (its autodetect table:
`show version` for `arista_eos` and `hp_procurve`) or when ntc-templates 3.5.0's index (in CI's
environment) parses it for that platform. Everything else is **(inferred)**, from vendor
command-line conventions, and is to be checked on the switch.

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

**Comware** (an HP 5130 or 5900) speaks `display`, which the read-only allowlist does not
have. A Comware switch cannot be read this way.

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
  which is the lock change; or Comware, which is not covered here.
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

## 5. What this does not do

- It has no driver: no deploy, verify, golden or drift.
- It creates no NetBox record: step 1 is a gap.
- It doesn't read Comware.
- It doesn't change the netmiko lock for AOS-CX.
- Its masking cases are line shapes, not captures. A real capture's lines replace them after
  the sitting.
