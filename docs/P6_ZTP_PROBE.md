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
| P-M2d | (added after the re-run, with `CLAB_MGMT_PASSTHROUGH`) Is Gi1 left unanswered? | Yes: Gi1's DISCOVERs appear on the probe's docker bridge and go unanswered, AutoInstall keeps asking on both interfaces, and no `Acquired IPv4 address … GigabitEthernet1` line appears |

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

### Observed: M1 re-run on the same node, after `write erase` and `reload` (2026-09-26)

The erase was done on the device (answering `no` to "Save?"), so this run
tests the diagnosis. It does not test `944876c`'s disk fix, which has not yet
booted a fresh node.

| # | Observed |
|---|---|
| P-M0 | **Passed**: `No startup-config, starting autoinstall/pnp/ztp...`. The install overlay's NVRAM was the whole cause |
| P-M1 | **Yes**: `Autoinstall trying DHCPv4 on GigabitEthernet1,GigabitEthernet2`. IOS-XE brings both interfaces up itself. The first run's "administratively down" came from the saved config, not the platform |
| P-M2b | **Holds**: DHCPDISCOVERs from `aa:bb:cc:00:02:50` on `br-mgmt` at 00:23:13, 00:23:20 and 00:23:24, unanswered (nothing reserved, correct for M1). Also RARP requests, AutoInstall's older path |
| P-M2c | **Holds, and it decides the next step**: Gi1 was answered first (`Acquired IPv4 address 10.0.0.15 on Interface GigabitEthernet1 … si-addr 10.0.0.2`), then `stop Autoip process`. AutoInstall takes the first answer and stops |
| (none) | **Unpredicted: PnP reached the internet.** `PNP_CCO_SERVER_IP_RESOLVED: devicehelper.cisco.com` and `HTTP_CONNECTED … /pnp/HELLO`, then a 600 s backoff. Through Gi1's qemu DHCP, which handed out DNS `10.0.0.3` and a route out through the lab host. A PnP HELLO carries the device's UDI (product ID and serial number), so a configless node on a network with a way out identifies itself to Cisco before it finds anything local. P6_ZTP.md D4 is the design consequence |

**So the branch at step 6 is "DISCOVERs on br-mgmt", corrected for Gi1.**
Section 9's option (e) removes Gi1's answer inside containerlab; option (d)
removes it with a Proxmox VM.

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

The last line must be `REFUSED: already patched`, and the patched file's
sha256 must be `972a0f72f1ee5847…` (computed from the fixture by the
patcher at `a5f5b530…`, which also says which disk it boots). **A hash taken
here is a hash of the staged file, not of the running one:** after the
deploy, step 4 hashes `/launch.py` INSIDE the container, and that is the
check that counts. **The patcher never upgrades an older configless copy:**
a mark says "patched" and not with which edits, so re-staging starts from the
adopted base (the `cp` above overwrites the copy) and the patcher applied to
that. The base is unchanged at `e483dd2475b505bd…`; only the edits changed.

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

- directory `/etc/kea/nmas/`, owned `dmarchak:_kea`, mode `0755` (first
  specified `0750`; see "As run" below for why it changed);
- file `/etc/kea/nmas/reservations-255.json`, owned `dmarchak:_kea`, mode
  `0644` (first specified `0640`), holding `[]`;
- subnet `id: 255` (`10.255.0.0/24`) in `kea-dhcp4.conf` gets
  `"reservations": <?include "/etc/kea/nmas/reservations-255.json"?>`.

**Measured before writing the commands (2026-09-26, read-only):**

- Subnet 255's block holds `"reservations": []` at line 91, so the edit is
  one line, a replacement.
- Kea's AppArmor profiles (`usr.sbin.kea-dhcp4`, `usr.sbin.kea-ctrl-agent`)
  allow reads of `/etc/kea/**`. So the fragment's directory must be UNDER
  `/etc/kea`: a fragment anywhere else would be refused by the profile
  whatever its mode. `/etc/kea/nmas/` satisfies both constraints.
- The tool already reads Kea through the Control Agent: `config-get` is ok,
  subnet 255 shows `reservations: []` and no option data, and
  `reservation_for('aa:bb:cc:00:02:50')` answers `not_reserved`.

**As run (2026-09-26), and why the modes are not the ones first specified.**
D1 is in place: `kea-dhcp4 -t` exit 0, Kea restarted clean (`NRestarts=0`,
no journal errors), and through the Control Agent subnet 255 reads
`reservations: []` and `option-data: []` from the RUNNING server, so D4's
posture holds in memory as well as in the file. The include syntax was
accepted at once. The first `-t` failed on ACCESS, with this in the kernel
log:

```text
apparmor="DENIED" operation="capable" profile="kea-dhcp4" capability=2 capname="dac_read_search"
apparmor="DENIED" operation="capable" profile="kea-dhcp4" capability=1 capname="dac_override"
```

**Kea's AppArmor profile withholds the two capabilities that let root ignore
file modes**, so `kea-dhcp4` run as root under `sudo` is held to the mode
bits. Root is neither `dmarchak` nor in `_kea`, so `0750`/`0640` shut it
out. The path was never the problem: the profile does allow `/etc/kea/**`,
which is why it would have read as a path problem indefinitely. The same log
holds an older instance, `/tmp/kea-broken.conf`, denied on 2026-09-25 during
the operator's config-test control.

**The modes are `0755` on the directory and `0644` on the file** (the
operator's decision). The asymmetry decided it: the RUNNING daemon executes
as `_kea` and could read `0640`. Only the offline `kea-dhcp4 -t`, as root,
could not. So `0640` would have worked in production and made the syntax
check unusable, and a config that cannot be validated offline is found out
at restart. The fragment holds MAC-to-address reservations: inventory, not
secrets, already in NetBox and the manifest. The tool still has what the
design needs: it owns the directory and writes by temp-then-rename.

The commands below are the ones that were run, with the measured modes.

```bash
sudo cp -a /etc/kea/kea-dhcp4.conf /etc/kea/kea-dhcp4.conf.bak-pre-d1
ls -l /etc/kea/kea-dhcp4.conf.bak-pre-d1

sudo install -d -o dmarchak -g _kea -m 0755 /etc/kea/nmas
sudo install -o dmarchak -g _kea -m 0644 /dev/null /etc/kea/nmas/reservations-255.json
printf '[]\n' > /etc/kea/nmas/reservations-255.json
ls -ld /etc/kea/nmas && ls -l /etc/kea/nmas/reservations-255.json
sudo -u _kea cat /etc/kea/nmas/reservations-255.json
```

Expect `drwxr-xr-x dmarchak _kea`, `-rw-r--r-- dmarchak _kea`, and `[]` read
back AS `_kea`. Reading it as `_kea` covers the daemon; the `kea-dhcp4 -t`
below, as a confined root, is the reader that decided the mode. The `printf`
runs as `dmarchak` and writes into an existing file, so owner, group and
mode stay as `install` set them.

Then the one-line edit. Line 91 changes from `"reservations": []` to
`"reservations": <?include "/etc/kea/nmas/reservations-255.json"?>`:

```bash
sudoedit /etc/kea/kea-dhcp4.conf
diff /etc/kea/kea-dhcp4.conf.bak-pre-d1 /etc/kea/kea-dhcp4.conf
sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf
```

The `diff` must show exactly that one line and nothing else. `-t` parses
without touching the running server; if it refuses the include inside a
value, stop here, since the running server is untouched. Then:

```bash
sudo systemctl restart kea-dhcp4-server
systemctl show -p ActiveState,SubState,MainPID,NRestarts kea-dhcp4-server
journalctl -u kea-dhcp4-server -n 15 --no-pager
```

**What D1's readback can and cannot show.** An empty reservation list reads
identically before and after the edit, so reading back `[]` cannot show that
the include is live. It shows only that Kea started with the edited file.
The include is proven live by M5 step 3, where a reservation written ONLY
into the fragment appears in `config-get`. Rollback, if needed:
`sudo cp -a /etc/kea/kea-dhcp4.conf.bak-pre-d1 /etc/kea/kea-dhcp4.conf`
then the restart above.

### M5 — does a reservation survive a reload AND a restart (the operator's first requirement)

This is the measurement that catches D1 being wrong, and the first one that
can show the include is LIVE: an empty list reads the same either way.

**The instrument:** `docs/bootstrap-probe/kea-m5.py`. It talks to
kea-dhcp4's own control socket, so it needs no API credential and no
netcat. The socket is `srwxr-xr-x _kea`, and connecting to a unix socket
needs write permission, hence `sudo`. It never writes a file and never
calls `config-write`. `tests/test_kea_m5_helper.py` drives it against a fake
Kea socket, and three controls each failed their targets.

**The control is a SECOND reservation, `aa:bb:cc:00:02:51 -> 10.255.0.51`**,
not the same one. Both then read back side by side, and the restart
separates them in one step: the file's survives and memory's does not.

Run from the deployed checkout (`H=` is not used; every line names the
path in full):

```bash
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show
```

Step 1. Expect `0 reservation(s); option-data: []`, the baseline.

Step 2, the fragment, written the way the tool will write it
(temp-then-rename, mode set explicitly, never inherited from the umask, which
is `0002` in this shell):

```bash
install -m 0644 /dev/null /etc/kea/nmas/.reservations-255.json.tmp
printf '[ { "hw-address": "aa:bb:cc:00:02:50", "ip-address": "10.255.0.50" } ]\n' > /etc/kea/nmas/.reservations-255.json.tmp
mv -f /etc/kea/nmas/.reservations-255.json.tmp /etc/kea/nmas/reservations-255.json
ls -l /etc/kea/nmas/reservations-255.json && cat /etc/kea/nmas/reservations-255.json
sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf; echo "config-test exit=$?"
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show
```

The rename leaves the file `dmarchak:dmarchak 0644`, because a rename brings
the new inode's owner. With `0644` the group no longer decides anything, which
is the D1 mode doing its job. The last `show` is a control of its own:
**predicted 0 reservations**. The file has changed and the running server has
not re-read it, so a 1 here would mean the reading does not come from where it
claims.

Step 3, reload, then read:

```bash
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py reload
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show
```

**Predicted: 1 reservation, `aa:bb:cc:00:02:50 -> 10.255.0.50`.** This is the
line that shows the include is live. Tell me when it is there, and I read it
through the tool's `reservation_for()` as well (the Control Agent path, the
one the build uses).

Step 4, the control, in memory only:

```bash
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py control-set aa:bb:cc:00:02:51 10.255.0.51
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show
```

**Predicted: 2 reservations**, `.50` and `.51`.

Step 5, the restart that separates them:

```bash
sudo systemctl restart kea-dhcp4-server
systemctl show -p ActiveState,SubState,MainPID,NRestarts kea-dhcp4-server
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show
```

**Predicted: 1 reservation, `.50` only.** `.51` gone is C49's failure shown
happening, and `.50` present is D1 preventing it. A reload is deliberately
NOT run between steps 4 and 5: a reload also re-reads the file and would drop
`.51` too, so a reload could not tell the file from a restart.

**What M5 leaves behind is what M3 needs:** `.50` reserved for the probe's
pinned MAC, address only. M3 adds its config-source options. To clear it
later, write `[]` the same way and reload.

### M3 — which transport and filename the node asks for

**M5's result (2026-09-26), which M3 builds on.** Every prediction held. The
show before any write read 0; after the file was written and config-test
passed it STILL read 0, so the helper reads the daemon and not the file.
After the reload, `.50` was present: the include is live. After the
config-set control, `.50` and `.51`. After the restart, `.50` only (MainPID
773857, `NRestarts=0`). The tool's `reservation_for()` reads `.50` as
`reserved` through the Control Agent, so both paths agree. **D1 and C49 are
closed on measurement.** One precision for the record: `.51` was not put
through a reload. A reload re-reads the file, so it would have dropped `.51`
too. A config-set-only reservation vanishes at a reload AND at a restart,
which is why the step order kept the reload out.

**Measured for M3 before writing it (2026-09-26):**

- Kea 2.4.1 names `tftp-server-name` (66) and `boot-file-name` (67). It has
  no name for 150, which would need an option definition. So M3 offers 66
  and 67, the standard pair, and 66 carries an ADDRESS so no resolver is
  needed (D4).
- Nothing listens on udp/69 on the NMAS host, and ufw is active. That is
  fine for M3, which asks only WHAT the node requests: the request is on the
  wire whatever answers it. Serving it is M4.
- containerlab's docker bridge for a network is `br-` plus the first 12
  characters of the network ID (`clab-r6` is `br-2ffe86702089`).

**The reservation M3 adds to.** Both options are `always-send`, so what the
node is offered does not depend on what it requests, and the wire shows
exactly that. The filename is the device's name. Only the requesting
address will decide what M4's responder serves (section 10), so the name is
for the reader:

```bash
install -m 0644 /dev/null /etc/kea/nmas/.reservations-255.json.tmp
printf '[ { "hw-address": "aa:bb:cc:00:02:50", "ip-address": "10.255.0.50", "option-data": [ { "name": "tftp-server-name", "data": "10.255.0.10", "always-send": true }, { "name": "boot-file-name", "data": "bp-ztp-a.cfg", "always-send": true } ] } ]\n' > /etc/kea/nmas/.reservations-255.json.tmp
mv -f /etc/kea/nmas/.reservations-255.json.tmp /etc/kea/nmas/reservations-255.json
cat /etc/kea/nmas/reservations-255.json
sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf; echo "config-test exit=$?"
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py reload
sudo python3 /home/dmarchak/python/Agentic_NMAS/docs/bootstrap-probe/kea-m5.py show
```

Expect `aa:bb:cc:00:02:50 -> 10.255.0.50  [tftp-server-name=10.255.0.10,
boot-file-name=bp-ztp-a.cfg]` and `D4: no route or resolver option reaches a
reservation here`. `show` now applies D4's refusal list over global,
shared-network, subnet and reservation option data, and exits 1 on a hit. It
is the preview of the check the build will carry, so M3 cannot start with
the posture broken.

**The captures, all started BEFORE the deploy** (the Gi1 one right after it,
because the deploy creates its bridge; the VM takes minutes to reach
AutoInstall, so it is still before the boot):

Lab host, terminal A (the lab segment, as in M1):

```bash
sudo tcpdump -ni br-mgmt -e -w /tmp/ztp-a-m3.pcap ether host aa:bb:cc:00:02:50
```

Lab host, terminal B, live:

```bash
sudo tcpdump -ni br-mgmt -e -l ether host aa:bb:cc:00:02:50
```

NMAS host, terminal C (what reaches the host, before its firewall decides):

```bash
sudo tcpdump -ni enp6s19 -w /tmp/ztp-a-m3-nmas.pcap host 10.255.0.50 or ether host aa:bb:cc:00:02:50
```

Deploy (lab host), then at once terminal D on the probe's own docker bridge
(Gi1 under passthrough):

```bash
cd /home/dmarchak/labs/ztp-a && sudo containerlab deploy -t nmas-ztp-a.clab.yml
sudo tcpdump -ni "br-$(docker network inspect -f '{{.Id}}' clab-ztp-probe | cut -c1-12)" -e -l port 67 or port 68
```

If the bridge name comes out as bare `br-`, the network does not exist and
tcpdump says so: stop there.

**Before anything else, the file the container RUNS** (M3's first run was
lost to a stale bind, found only by hashing inside the container):

```bash
docker exec clab-nmas-ztp-a-bp-ztp-a sha256sum /launch.py
docker logs clab-nmas-ztp-a-bp-ztp-a 2>&1 | grep -E "CONFIGLESS|Creating overlay disk image"
```

Expect `972a0f72f1ee5847…`, then these three lines in this order:

- `CONFIGLESS: booting the base disk /c8000v-universalk9_8G_serial.17.06.01a.qcow2`
- `CONFIGLESS: removing /c8000v-universalk9_8G_serial.17.06.01a-overlay.qcow2 …`
- `Creating overlay disk image: /c8000v-universalk9_8G_serial.17.06.01a-overlay.qcow2`

That last name has ONE `-overlay`. `-overlay-overlay` means the install
overlay was booted again. If the hash or any of the three lines differs,
tear down before the console. Then watch the log (terminal E):

```bash
docker logs -f clab-nmas-ztp-a-bp-ztp-a
```

Then the console, answering NOTHING for 15 minutes, as in M1 step 5.

### Observed: M3's first run (2026-09-27), and why it does not count

**P-M0 failed, and the cause was the instrument: the container ran the OLD
launch script.** Measured inside the running container and on the lab host:

- `docker inspect` binds `/home/dmarchak/labs/ztp-a/patches/c8000v-launch-configless.py`
  to `/launch.py`.
- That file, and `/launch.py` inside the container, hash to `5d0a4b73…`.
  That is exactly the four-edit patcher's output from the base, recomputed
  here from `fd85451`'s patcher. Its line 90 has no `-overlay` filter and
  there is no removal block.
- Its mtime is `2026-09-26 23:43:40`, the original staging, before the new
  patcher arrived (`00:38:05`). So the re-staging's `cp` and `--write` did
  not run against THIS path, whatever produced the `258c1633…` that was
  read.
- Everything the node did follows from that. The script handed vrnetlab the
  install overlay, vrnetlab created `-overlay-overlay` on it (the log line
  and `qemu-img info -U` agree), and the node booted the saved config:
  `platform console serial`, and Gi2 in `shutdown`.

**P-M2d: passthrough took effect.** The qemu line shows Gi1 as
`-netdev tap,id=p00,ifname=tap0,script=/etc/tc-tap-mgmt-ifup`, not a user
network. Whether its DISCOVERs went unanswered is for the Gi1 capture. P-M3
was not reached: Gi2 was shut down by the saved config. The config ISO was
generated (`/config.iso`, 01:05:13) and NOT attached (no `-cdrom` on the
qemu line), so the ISO edit held.

**Recorded, not explained:** `show startup-config` read `Last configuration
change at 01:12:08` on this boot, 5 s before the console was released. So
something re-saved NVRAM during a boot of the INSTALL overlay. The
hypothesis that IOS-XE writes a startup config on a configless first boot
is refuted by M1's re-run, where an erased NVRAM gave `No startup-config,
starting autoinstall` and no config. What re-stamped an inherited config is
open. The fresh-base boot will show whether any write happens with nothing
inherited.

**The instrument's own gap:** the removal was logged only when it removed
something, so a missing line could not tell "patch absent" from "nothing to
remove". The patch now says which disk it boots, and says "nothing to
remove" when there is nothing, in every case (`TestItSaysWhatItDid`, two
controls fired). The runbook reads the file the CONTAINER runs before
anything else.

**Predictions, recorded before the boot:**

| # | What will be seen | Prediction |
|---|---|---|
| P-M0 | The disk fix, on a FRESH node | `/launch.py` in the container is `972a0f72…` and the log carries the three lines above; the console says `No startup-config, starting autoinstall/pnp/ztp`; `show startup-config` reports none. No hand erase this time |
| P-M2d | Passthrough | DISCOVERs from Gi1's MAC on the docker bridge (terminal D), none answered; no `Acquired IPv4 address … GigabitEthernet1` |
| P-M3a | Gi2 is answered by Kea | DISCOVER, OFFER, REQUEST, ACK on `br-mgmt`; `Acquired IPv4 address 10.255.0.50 on Interface GigabitEthernet2` |
| P-M3b | What it asks for, and how | A TFTP read request for `bp-ztp-a.cfg` to `10.255.0.10:69`, seen on terminals A and C. Nothing answers it. Whether AutoInstall then tries its default names (`network-confg`, `cisconet.cfg`, `router-confg`, `ciscortr.cfg`) is recorded, not predicted |
| P-M3c | D4 on the device | No `PNP_CCO_SERVER_IP_RESOLVED`, no `HTTP_CONNECTED`: without a resolver or a route there is no path to Cisco |

After 15 minutes, answer `no`, press RETURN, and record:

```text
show startup-config
show ip interface brief
show interfaces GigabitEthernet2 | include bia
show logging | include PNP|DHCP|AUTOINSTALL|Autoinstall|TFTP|Acquired
```

Stop the captures and read them:

```bash
sudo tcpdump -nr /tmp/ztp-a-m3.pcap -e | head -60
```

and on the NMAS host:

```bash
sudo tcpdump -nr /tmp/ztp-a-m3-nmas.pcap | head -60
```

Tell me when the node has its lease and I will read it through the tool's
`lease_for()`, the call phase 2's discovery uses. **What M3 decides:** D2's
transport (TFTP by option 66/67 as offered, or something the node reaches
for instead), and whether M4 needs udp/69 opened in ufw with TFTP's
connection tracking, or a different transport. Teardown is step 7, as in
M1. Leave `.50`'s reservation in place for M4.

### Observed: M3, second run (2026-09-27): every prediction held but one

Before the console, `/launch.py` in the container hashed to `972a0f72…` and
the log carried the three lines in order, so the instrument was the one
intended this time.

| # | Observed |
|---|---|
| P-M0 | **Passed on a fresh node, with no hand erase:** `% Failed to initialize nvram`, then `No startup-config, starting autoinstall/pnp/ztp...`. The chassis serial changed too (`9ZPRULBCRA3`, not `9V5EGCL4W1N`), so this is the pristine base, not the install overlay |
| P-M2d | **Passed:** three DISCOVERs from Gi1 (`0c:00:03:50:8d:00`) on the probe's docker bridge, unanswered, and `SETUP: new interface GigabitEthernet1 placed in shutdown state` |
| P-M3a | **Passed:** `Acquired IPv4 address 10.255.0.50 on Interface GigabitEthernet2`, with the full DORA on `br-mgmt` (01:29:48–01:30:18). **The reservation the tool's mechanism wrote answered a device that asked** |
| P-M3b | **Passed:** `RRQ "bp-ztp-a.cfg" octet` (21 bytes, so no TFTP options) to `10.255.0.10:69`, retried for two minutes with backoff, each answered `ICMP udp port 69 unreachable`. **D2's transport is decided by measurement: TFTP, port 69, the filename from option 67** |
| P-M3c | **Refuted, and the refutation sharpens D4:** 8 DNS queries for `tools.cisco.com` (A and AAAA) sent to `255.255.255.255:53`, broadcast because the node has no resolver, and 0 replies. D4's posture stopped the node REACHING Cisco; it did not stop it TRYING, in the open, on the segment |

**Read from the capture (read-only, on the lab host), beyond the operator's
report:**

- **Kea's ACK carried exactly** mask, hostname, lease times (51, 58, 59),
  server ID, client ID, 66 (`10.255.0.10`) and 67 (`bp-ztp-a.cfg`). **No 3
  and no 6: D4's posture is shown on the wire**, not only in the config.
- **`hostname: router` is an ECHO, not a configured level.** The node sent
  `Hostname (12) "Router"` in its DISCOVER and REQUEST, and Kea returned it
  lowercased. So it came from the request, and no level of Kea's config
  held it. Kea echoes client-identity options (12, 61) and nothing else, so
  no echo can deliver a route or a resolver. D4's enumeration of CONFIGURED
  levels stays complete for its four codes.
- **The node ASKS for what D4 withholds.** Its parameter request list is 1,
  66, **6**, 15, 44, **3**, 67, 12, **33**, 150, 43, 125. Kea sends an
  option the client requests, so a 3 or 6 at any level would have been
  delivered. That is why D4 must be a check rather than a default. Its
  vendor class is `ciscopnp`, and it asks for 43 (a PnP server).
- **Nothing on the segment answers DNS:** the NMAS host listens on
  `127.0.0.53`/`.54` only, and none of the nine fleet goldens carries
  `ip dns server`. A host that answered broadcast DNS would hand the node a
  resolver with no DHCP option at all. So "nothing answers DNS on the ZTP
  segment" is D4's second condition (P6_ZTP.md).
- **The name is not PnP's.** M1's re-run resolved `devicehelper.cisco.com`
  (the PnP redirect); these ask for `tools.cisco.com`, Cisco's Call Home
  endpoint (Smart Licensing's call-home transport). So a second subsystem
  reaches for Cisco. Which one is not established by the capture. On the
  console, `show call-home profile all | include tools`,
  `show license status | include Transport|URL` and
  `show logging | include CALLHOME|SMART_LIC` would say.

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
- **(e) vrnetlab's management passthrough (found after M1's re-run, by
  reading `/vrnetlab.py`).** With the node environment
  `CLAB_MGMT_PASSTHROUGH: "true"`, `gen_mgmt()` builds Gi1 as a tap mirrored
  onto the container's `eth0` instead of qemu's user network. So neither
  qemu's DHCP server nor its TFTP server exists any more. `eth0` sits on the
  probe's docker bridge (`clab-ztp-probe`), and docker runs no DHCP server.
  Gi1 still exists and still asks, and nothing answers it. That is the
  shape of a real device with an unserviced port, and it needs no Gi1 cable,
  so the reserved-interface rule is not involved. **It is read, not
  measured.** Its prediction (P-M2d): DISCOVERs from Gi1's MAC appear on the
  docker bridge and go unanswered, and AutoInstall keeps asking on both
  interfaces. Cost: one environment line in the topology. If it fails, (d)
  is next.
- **(b) as the operator framed it, letting Gi1 be answered, is not viable:**
  `stop Autoip process` ends discovery at the first lease. Its variant (put
  the bootstrap config in the container's `/tftpboot`, which qemu serves to
  Gi1) would work, and would demonstrate vrnetlab's plumbing rather than Kea,
  the tool's responder or the lab segment. Rejected on that ground.

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
