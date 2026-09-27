# P.6 probe — ZTP, starting with measurement 1

**Subject: `bp-ztp-a`, a throwaway.** Scope and the three decisions:
[P6_ZTP.md](P6_ZTP.md) (D1 an include fragment the tool owns, D2 a responder
in the tool, D3 the server address derived from Kea). Topology:
`docs/bootstrap-probe/nmas-ztp-a.clab.yml`.

**The pair, written here and in the topology:** `aa:bb:cc:00:02:50 -> 10.255.0.50`.

Every command names its paths in full. No step depends on a variable, a `cd`
or a shell set up by an earlier step.

---

## What measurement 1 touches

**Nothing on the NMAS, nothing in NetBox, nothing in Kea.** It boots one node
on the containerlab host and watches. There is therefore no census baseline
and no temporary list for M1. Both are needed from M4, where a device is
onboarded.

---

## Established by reading, before anything booted

Read from the adopted launch script (sha256 `e483dd24…`, identical in all
three probe copies on the lab host) and from `/vrnetlab.py` inside a running
node:

1. **vrnetlab always gives a C8000v a day-0 config.** It writes one into
   `config.iso` (`/iosxe_config.txt`, applied by IOS-XE's CVAC) and attaches
   it with `-cdrom`. With no startup file it still builds its own. So an
   UNMODIFIED node never boots configless, and IOS-XE runs AutoInstall/PnP
   only without a startup config. **Prediction 1 holds, and it held without a
   boot.**
2. **The launch script marks a node running only on `CVAC-4-CONFIG_DONE`,
   and after 300 quiet console spins it RESTARTS the VM.** A configless node
   never prints `CONFIG_DONE`, so the watchdog would restart it silently in
   the middle of whatever it was doing.
3. **Gi1 is qemu's user-mode network**, with its own DHCP server
   (`dhcpstart=`) and a TFTP server on `/tftpboot`, which is empty.
4. **Removing the ISO is not enough: the DISK already holds a startup
   config.** Found by reading, after the first version of the variant was
   written and before anything booted it. The image carries two disks (read
   from `/` inside r6's container, with `qemu-img info`):
   - the Cisco base, `c8000v-universalk9_8G_serial.17.06.01a.qcow2`, 1.49 GiB,
     with no backing file;
   - an overlay the image build's install step wrote into,
     `…17.06.01a-overlay.qcow2`, 311 MiB, backed by the base. The install
     config ends `do wr`, so a startup config is saved in it.

   The launch script takes the first `.qcow2` in sorted order. `-` sorts
   before `.`, so it takes that overlay, and vrnetlab creates the run-time
   overlay (`…-overlay-overlay.qcow2`, found dated the day it was read) on
   top of it. **The saved config is real, not inferred:** r6's first golden
   carries `platform console serial` and `license boot level
   network-premier addon dna-premier`, lines that only the install config
   writes. Neither vrnetlab's run-time bootstrap nor the tool's generator
   emits them. With only the first version of the variant, the node would
   have booted that saved config, run no discovery, and P-M1 would have read
   "no". That answer would have been about the instrument, not the platform.

So the probe binds a **configless variant**, made by
`docs/bootstrap-probe/patches/patch-configless.py` from the adopted copy. It:

- boots the BASE disk, never an overlay;
- removes the install overlay from this container's own writable layer
  before the VM starts. vrnetlab names the run-time overlay
  `<disk>-overlay.qcow2` and reuses one that exists, so this removal is
  what makes the run-time overlay a fresh one over the pristine base. The
  image itself is untouched;
- attaches no config ISO at run time;
- accepts IOS-XE's own prompt as "running", and releases the console;
- never restarts a quiet VM.

`tests/test_configless_patch.py` checks each of these against the real
script. The disk choice is checked by EXECUTING the script's constructor on
a fake root: unpatched, it hands vrnetlab the install overlay; patched, the
base, with exactly the install overlay removed. Six controls, each failing
its target.

**A consequence to know before M3-M5:** the removal runs in the constructor,
so it runs at every CONTAINER start. Restarting the probe's container
discards whatever the node saved. An IOS `reload` inside the running
container does not re-run the constructor.

**What this means for the write-up (the operator's point, recorded before the
run):** if the node asks for a config only because the probe removed
vrnetlab's day-0 config, Lab 8 demonstrates the TOOL's half (a reservation
written, a config served and recorded, a device reached) against a node that
had to be PERSUADED to ask. The write-up must say so, and must not imply that
a stock vrnetlab node bootstrapped itself.

---

## Predictions, recorded before step 4

| # | What will be seen | Prediction |
|---|---|---|
| P-M0 | Did the node really boot with no startup config? (the instrument, checked before P-M1 means anything) | Yes. The container log names the removed install overlay, and `show startup-config` reports none. A "no" here voids every later row: it is the variant failing, not the platform |
| P-M1 | Does the configless node start AutoInstall, PnP or ZTP? | Yes: with no startup config, IOS-XE 17.6 begins discovery on its own. The console shows PnP or AutoInstall messages, and/or DHCP requests leave the node |
| P-M2a | Is Gi1 answered? | Yes, by qemu's DHCP, within seconds. If AutoInstall runs, it may try TFTP against qemu's server on Gi1 and find nothing |
| P-M2b | Does a DHCPDISCOVER from `aa:bb:cc:00:02:50` appear on `br-mgmt`? | Yes, and it gets no offer (the MAC is unreserved on a pool-less subnet) |
| P-M2c | Does Gi1's answer stop discovery before Gi2 is tried? | Unknown. This is the measurement most likely to decide the lab |

### Observed: M1, run 2026-09-26 with the FOUR-edit variant (before the disk edits)

- `%PNP-6-PNP_DISCOVERY_STARTED` at 23:53:54, then
  `%PNP-6-PNP_DISCOVERY_STOPPED: PnP Discovery stopped (STARTUP CONFIG PRESENT)`
  14 s later. **PnP runs on this platform, and it stopped because the node
  had a startup config.**
- `GigabitEthernet1 … YES NVRAM administratively down`: an address method
  read from NVRAM. `GigabitEthernet2 … YES unset administratively down`.
- On `br-mgmt`: no DHCPv4 at all. IPv6 only from `aa:bb:cc:00:02:50`
  (MLDv2, one NS, and RS backing off from 4 s to 242 s). `bia` is
  `aabb.cc00.0250`, so the MAC pin held.
- `show pnp summary` does not exist on 17.6.1a.

**Reading:** P-M0 failed, and it failed for the reason item 4 of "Established
by reading" gives: the node booted the install overlay's saved config. The
operator reached the same cause from the device side (`Method: NVRAM`)
independently of the reading. So P-M1 is **not answered** by this run; what
it established is that PnP exists here and defers to a startup config.
P-M2c is untested: nothing got as far as asking.

**One observation does not fit yet:** Gi2 reads administratively down at the
end, while its MAC was sending IPv6 RS for minutes. Something had it up for a
while. The capture's last RS time against the time `show ip interface brief`
ran would say when it went down. Recorded, not explained.

---

## Step 1 — stage the probe's own configless copy (lab host)

The probe directory and its own copy. Never a production lab's file (the
patcher refuses `labs/lab/` and `labs/r6/`).

```bash
mkdir -p /home/dmarchak/labs/ztp-a/patches
cp /home/dmarchak/labs/dhcp-a/patches/c8000v-launch-adopted.py /home/dmarchak/labs/ztp-a/patches/c8000v-launch-configless.py
sha256sum /home/dmarchak/labs/ztp-a/patches/c8000v-launch-configless.py
```

Expect `e483dd2475b505bd…`. Anything else is a different base, so stop.

Copy the patcher and the topology over from the repository. Then read the
diff, which writes nothing:

```bash
python3 /home/dmarchak/labs/ztp-a/patches/patch-configless.py /home/dmarchak/labs/ztp-a/patches/c8000v-launch-configless.py
```

Six hunks: the base disk, the install overlay, the `-cdrom` guard, the
console wait, the running branch, and the watchdog. Then apply and confirm:

```bash
python3 /home/dmarchak/labs/ztp-a/patches/patch-configless.py /home/dmarchak/labs/ztp-a/patches/c8000v-launch-configless.py --write
python3 -m py_compile /home/dmarchak/labs/ztp-a/patches/c8000v-launch-configless.py && echo COMPILES
python3 /home/dmarchak/labs/ztp-a/patches/patch-configless.py /home/dmarchak/labs/ztp-a/patches/c8000v-launch-configless.py
```

The last line must be `REFUSED: already patched`.

## Step 2 — confirm nothing collides (lab host, and the NMAS host)

```bash
docker network ls --format '{{.Name}}' | xargs -n1 docker network inspect -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}'
ip -br link show master br-mgmt
```

`172.30.80.0/24` must be absent, and `br-mgmt` must hold `enp6s19`,
`s3-mgmt` and `r6-mgmt` only. On the NMAS host, confirm `10.255.0.50` is
neither reserved nor leased:

```bash
grep -c '10.255.0.50' /etc/kea/kea-dhcp4.conf
sudo grep -c 'aa:bb:cc:00:02:50\|10.255.0.50' /var/lib/kea/kea-leases4.csv
```

Both must print `0`.

## Step 3 — start the observers BEFORE the boot

A result is only as good as the observer that was running when it happened.

**Lab host, terminal A** (the wire; this is the discriminator, because Kea
logs an unanswered DISCOVER only at debug level):

```bash
sudo tcpdump -ni br-mgmt -e -w /tmp/ztp-a-m1.pcap ether host aa:bb:cc:00:02:50
```

**Lab host, terminal B** (a live view of the same):

```bash
sudo tcpdump -ni br-mgmt -e -l ether host aa:bb:cc:00:02:50
```

Record the time:

```bash
date -u +%FT%TZ
```

## Step 4 — deploy (lab host)

```bash
cd /home/dmarchak/labs/ztp-a && sudo containerlab deploy -t nmas-ztp-a.clab.yml
docker logs -f clab-nmas-ztp-a-bp-ztp-a
```

In the container log, expect *"User provided startup configuration is not
found"*, then **`CONFIGLESS: removing /c8000v-universalk9_8G_serial.17.06.01a-overlay.qcow2`**
(P-M0's first half; if it is absent, stop and tear down, because the node is
booting the saved config), then the VM booting. The line that matters next is
**`CONFIGLESS: console ready without a day-0 config`**. If instead you see
`CONFIGLESS: 300 quiet spins; NOT restarting the VM`, the VM is quiet and was
NOT restarted, which is the variant working. Keep watching.

## Step 5 — the console, WITHOUT answering anything for 15 minutes

```bash
docker exec -it clab-nmas-ztp-a-bp-ztp-a telnet 127.0.0.1 5000
```

**Do not answer the configuration dialog.** On IOS-XE, answering it can end
AutoInstall. For 15 minutes, only watch and copy what appears:

- lines naming PnP (`%PNP-…`);
- lines naming AutoInstall or TFTP (`network-confg`, `router-confg`,
  `ciscortr.cfg`);
- DHCP lines naming an interface or an address.

**If the console stays silent past 15 minutes**, suspect the console before
concluding anything about discovery. The `_serial` build should put the
console on serial itself, but the install config also set `platform console
serial`, and the configless boot no longer has that line. A silent console
and a silent node look the same from here, so check the wire (terminal B)
before recording "nothing".

After 15 minutes, answer `no`, press RETURN, and record:

```text
show startup-config
show ip interface brief
show interfaces GigabitEthernet2 | include bia
show pnp summary
show logging | include PNP|DHCP|AUTOINSTALL|TFTP
```

`show startup-config` must report no startup config (P-M0's second half).
`bia` must be `aabb.cc00.0250`. If either is not, that is the first finding,
and nothing about Kea may be concluded, exactly as in Phase 2.

## Step 6 — read it against the predictions

Stop both captures (Ctrl-C). Then:

```bash
sudo tcpdump -nr /tmp/ztp-a-m1.pcap -e | head -40
```

Write each result into the predictions table as **observed**, beside the
prediction. Then take the branch that the evidence selects:

| Observed | Meaning | Next |
|---|---|---|
| DISCOVERs from `aa:bb:cc:00:02:50` on `br-mgmt` | The node asks on the lab segment, and Gi2 is usable for ZTP | M3 (section 8) |
| Gi1 answered, AutoInstall tried TFTP on Gi1, nothing on `br-mgmt` | Discovery is satisfied by qemu's network and never reaches the lab segment | Section 9. Its option (d), the node as its own Proxmox VM, is scoped in section 11 and is the one that removes Gi1's answer rather than working around it |
| Nothing at all: the dialog, no PnP, no DHCP | This build does not discover without a PnP server | Section 9 |

## Step 7 — teardown (lab host)

```bash
cd /home/dmarchak/labs/ztp-a && sudo containerlab destroy -t nmas-ztp-a.clab.yml --cleanup
ip -br link show master br-mgmt
docker network ls --format '{{.Name}}' | grep -c ztp-probe
```

`br-mgmt` must be back to its three members, and the last line must print
`0`. Keep `/home/dmarchak/labs/ztp-a/patches/` for M3-M5, and delete
`/tmp/ztp-a-m1.pcap` once its result is copied into this document.

---

## 8. Later measurements, not yet runnable

These are written now so their predictions and controls exist before the
evidence. Each needs D1's one-time Kea change first.

### D1's one-time change (the operator's, on the NMAS host)

**The fragment gets a DIRECTORY the tool owns, not only a file.** The tool
writes by temp-then-rename, and that needs write permission on the directory.
`/etc/kea` is `root 755`, so a fragment directly inside it would force the
tool to truncate the file in place, which is the mechanism that erased
`user_settings.json` on 2026-09-23.

- directory `/etc/kea/nmas/`, owned `dmarchak:_kea`, mode `0750`;
- file `/etc/kea/nmas/reservations-255.json`, owned `dmarchak:_kea`, mode
  `0640`, holding `[]`;
- subnet `id: 255` (`10.255.0.0/24`) in `kea-dhcp4.conf` gets
  `"reservations": <?include "/etc/kea/nmas/reservations-255.json"?>`.

Then `kea-dhcp4 -t /etc/kea/kea-dhcp4.conf` must pass (config-test, touching
nothing). Whether the include is accepted inside a value is itself measured
here, not assumed. Then restart Kea, and confirm the subnet reads back with
an empty reservation list.

### M5 — does a reservation survive a reload AND a restart (the operator's first requirement)

This is the measurement that catches D1 being wrong.

1. Write the `10.255.0.50` reservation into the fragment by hand. The writer
   is not built yet, and this measures the mechanism, not the code.
2. Run `config-test`, then `config-reload` through the Control Agent.
3. Read it back from `config-get` and through the tool's
   `reservation_for('aa:bb:cc:00:02:50')`.
4. `sudo systemctl restart kea-dhcp4-server`.
5. Read it back again, both ways.

**Prediction:** present at step 3 and at step 5.

**Control:** the same reservation added by `config-set` alone (memory
only), and the same restart. Predicted ABSENT after the restart, which is the
failure D1 exists to prevent, shown happening.

### M3 — which transport and filename the node asks for

Boot `bp-ztp-a` again with the reservation carrying option 67 (a filename)
and a server address. Record, from the wire and the console:

- TFTP or HTTP;
- the filename requested;
- the source address.

This decides D2's transport. Whether Kea 2.4.1 needs an option definition
for 150 is recorded here too.

### M4 — does the fetched config apply, and is the staged credential then accepted

Onboard `bp-ztp-a` through the wizard with source `ztp`, once the build exists
(census baseline and a temporary list first, exactly as in Phase 2). The
responder serves the bootstrap artefact. The node applies it, and Phase 2's
verify reaches it with the staged credential. **This is Lab 8.** Lab 9 is
Phase 2 and one intent deploy after it.

---

## 9. If the node never asks on the lab segment

Recorded now, so a disappointing M1 leads to a decision rather than an
improvisation:

- **(a) Persuade it, minimally.** A one-line day-0 config that enables DHCP
  on Gi2 and nothing else, so the node asks where Kea answers. The lab then
  demonstrates the tool's half against a persuaded node, and the write-up
  says so.
- **(b) vIOS instead.** vrnetlab types its config over the console there, so
  the configless variant is a different patch, and the platform may behave
  differently.
- **(c) A containerlab link on Gi1.** Not possible: vrnetlab owns Gi1, and
  the topology rules refuse it.
- **(d) The node as its own Proxmox VM**, with no qemu user network at all,
  so nothing answers before Kea. Scoped in section 11, not built.

---

## 10. The responder's controls (the operator's second requirement)

The responder serves a config carrying a LIVE credential. So "it serves only
a pending device" is a claim that stays true only until a state changes
underneath it. Each of these is a test with a negative control, run confined,
before the responder is trusted:

| Claim | Test | Control |
|---|---|---|
| Every fetch is a reveal row | A fetch writes one row: the requesting address, the device, and the hash of what was served, never the config | Remove the recording: the test fails |
| It serves only the reserved address | A request from any other address is refused and recorded, and nothing is served | Accept any source: the test fails |
| It serves only a PENDING device, decided at request time | Promote the device between two requests: the second is refused | Cache "pending" at start-up: the test fails |
| An abandoned device is not served | Abandon, then request: refused, recorded | Keep serving after abandon: the test fails |
| Nothing is kept | No file exists anywhere after a fetch, and the served bytes come from `bootstrap_artifact()` at request time | Write to a spool directory: the test fails |
| The served config is the committed one | The recorded hash equals a fresh render from committed intent | Serve a cached render after an intent edit: the test fails |

---

## 11. Fallback: the node as its own Proxmox VM (scoped 2026-09-26, NOT built)

**Why it exists.** If Gi1's qemu DHCP answers first and ends discovery before
Gi2 is tried (P-M2c), no containerlab variant removes that answer: vrnetlab
owns Gi1 and builds its user network in `/vrnetlab.py`. A VM that Proxmox
runs directly has no qemu user network at all, so nothing answers before
Kea. Scoped now, so step 6 leads to a prepared option rather than to a
decision made under pressure. **Not built: M1 may make it unnecessary.**

Each answer below says how it was established. The Proxmox facts were read
through the app's own auditor token (read-only), from the NMAS host.

### Q1. The image: a bootable disk, or does it need vrnetlab's install step?

**Measured: the base disk boots as it is, and it is the configless disk we
want.** The vrnetlab image carries the Cisco base
(`c8000v-universalk9_8G_serial.17.06.01a.qcow2`, 1.49 GiB, 8 GiB virtual, no
backing file). vrnetlab's install step BOOTED that base, so the base needs no
install to boot. What the install step added lives in the other overlay (see
"Established by reading", item 4): vrnetlab's user, `platform console
serial`, the license boot level, and `do wr`. A configless probe must not
have any of those. So the Proxmox path uses the base only, and it is
configless by construction, with no patch.

Getting it, in order of preference:

1. **The operator's original from Cisco**, compared by `sha256sum` against
   the base inside the image. Equal means one disk and two copies. Different
   means the image was built from another download, and that difference is
   recorded before anything boots.
2. **Extracted from the image without running it:** `docker create` then
   `docker cp <id>:/c8000v-universalk9_8G_serial.17.06.01a.qcow2 .` then
   `docker rm <id>`. Nothing starts, and no overlay comes along.

**Storage (measured):** `local` holds content type `import`, with 79.5 GiB
free, so the qcow2 can be imported from there (`qm set … import-from`).
`vmdata` (zfspool) has 425.9 GiB free and `local-lvm` 277.9 GiB, and either
holds the VM's disk.

**Not measured, and must be measured before this path is trusted:**

- **The machine type and firmware.** vrnetlab runs qemu with its own
  arguments. The Proxmox VM should match them rather than take Proxmox's
  defaults, so read the qemu command line from a running C8000v first
  (`docker exec clab-r6-r6 ps -o args= -C qemu-system-x86_64`) and copy the
  machine, CPU model and NIC model from it.
- **The console.** The `_serial` build should put the console on serial by
  itself, and the install overlay's `platform console serial` hides whether
  it does (the same risk as in step 5). The VM gets `serial0: socket`, and
  `qm terminal <vmid>` is the console.

### Q2. The network path, with br-mgmt left where it is

**Measured: no move is needed.** The NMAS VM (102) and the containerlab VM
(100) both have `net1` on Proxmox bridge **`vmbr10`**, and `net0` on `vmbr0` (the
`10.0.0.0/24` LAN). The NMAS's `10.255.0.10/24` is on its `vmbr10` NIC, and
it reaches `s3`'s `Vlan99` (`10.255.0.1`) on that `/24` without a router.
`s3` runs inside VM 100, whose only other NIC is on `vmbr0`, so `vmbr10` is
the wire behind `br-mgmt`. That is established from the NIC list and the
addressing, not read off the containerlab VM's interface MAC. A VM with a NIC on
`vmbr10` is therefore L2-adjacent to Kea and to `s3`'s `Vlan99`, exactly as
`bp-ztp-a`'s Gi2 is through `br-mgmt`. The production lab's plumbing is not
touched.

**Two NICs, not one, and the reason is in the tool, not the network.**
`bootstrap_config.RESERVED_INTERFACES` refuses `GigabitEthernet1` for the
`cisco_iosxe` dialect, because vrnetlab owns Gi1. On a Proxmox VM that fact
is false, but the rule is keyed on the PLATFORM, not on the deployment. So
the VM gets:

- `net0` = Gi1, `link_down=1`: no carrier, so nothing answers on it and no
  guess is made about it;
- `net1` = Gi2, `virtio=AA:BB:CC:00:02:50,bridge=vmbr10`: the pinned MAC,
  known before the first boot, exactly as the containerlab topology pins it.

That keeps the interface names identical to `bp-ztp-a`, so the reservation,
the bootstrap render and M3-M4's expectations carry across unchanged, and
nothing in the tool is edited for a probe. Whether the rule should be keyed
on the deployment instead is a question for a PERMANENT device (Q4), and is
recorded there.

### Q3. Resources

**Measured on node `pve`:** 40 CPUs (2 sockets), load average 18.5 / 18.2 /
18.0, CPU 44.4%, memory 72.6 of 125.8 GiB used, so about 53 GiB free.

| VM | State | Cores | Memory |
|---|---|---|---|
| 100 CSCI5840CLAB (the containerlab VM) | running | 24 | 80 GiB |
| 102 NMAS | running | 4 | 16 GiB |
| 201 mininet | running | 6 | 12 GiB |
| 202 controllers | running | 4 | 6 GiB |
| 203 clab-sdn | stopped | 8 | 16 GiB |

The probe VM would take vrnetlab's own sizing: 2 vCPU, 4 GiB. Memory fits
with about 49 GiB to spare. On CPU, allocation is already over the core count
(38 vCPU on running VMs) and it is not the limit. Load is. Taking the
operator's figure of about 2 cores for an idle C8000v, the node goes from
about 18.5 to about 20.5 of 40. **Affordable for a throwaway.** If 203 is
started while the probe runs, the numbers change and should be re-read.

### Q4. What it costs the model

**For a throwaway: nothing lasting, and that is the point of a throwaway.**
It is never promoted into a list that the sync, heartbeat alerting or backups
read, or it is abandoned at teardown, exactly as `bp-dhcp-a` was.
Teardown is `qm stop <vmid>` and `qm destroy <vmid> --purge`, run by the
operator. The app's Proxmox token is an auditor and must stay one: creating
VMs is not a privilege this tool should hold for a probe.

**If a ZTP device on Proxmox became PERMANENT, it would need five things, and
the first is a defect that exists today:**

1. **The device-to-lab map has no "not a containerlab device" answer**
   (register **C50**). `clab_target_for()` resolves an absent `clab_lab` AND
   an unknown one to rcn-lab1's `configs_dir` and `launch_patch`, and the
   `named: False` flag it sets is read by nothing. For this device,
   `persist()` would write a startup file into `labs/lab/configs/` that
   nothing boots, check it against rcn-lab1's launch patch, pass, and report
   the rotation persisted, while the device's real persistence (its own
   NVRAM) went unexamined. **A wrong thing looking like a working thing,
   through the map built to prevent it.** Latent today: measured on the
   host, the one named lab (`r6`) exists.
2. **A persistence target of a different KIND.** A Proxmox VM keeps its disk,
   so its startup config survives a reboot the way hardware does, and
   clab-sync is irrelevant to it. Persistence is `write memory` plus a
   read-back of `show startup-config` carrying the credential the tool holds,
   which is `verify_startup_carries_current()`'s question asked of the device
   instead of a file. A map entry would say `kind: native`, and `persist()`
   would take that path instead of the file stages.
3. **`RESERVED_INTERFACES` keyed on the deployment, not the platform**
   (Q2). With two NICs it never binds. With one, it would refuse the only
   interface the device has. A proxy population: "C8000v" stood in for
   "vrnetlab C8000v", true until the first C8000v that is not one.
4. **Backup.** Its disk would be on `vmdata` or `local-lvm` with no vzdump job,
   the same as every other VM here (B5/B6: none exists). It goes into
   `proxmox_backup_vmids` so `job_health` names the gap as a row.
5. **The ordinary rows:** a per-device heartbeat window, provisional until
   measured (C21's rule: a rate measured on one device is a fact about that
   device); an Oxidized entry; NetBox through phase 2; and none of them
   specific to Proxmox.

**What this changes about the write-up either way:** a Proxmox node is a
closer model of real hardware than a vrnetlab node, because nothing sits
between the device and the segment. If Lab 8 runs there, the write-up says
so, because that is a stronger claim (the platform asked unaided), not a
weaker one.
