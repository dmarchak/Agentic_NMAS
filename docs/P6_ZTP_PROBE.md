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

So the probe binds a **configless variant**, made by
`docs/bootstrap-probe/patches/patch-configless.py` from the adopted copy. It:

- attaches no config ISO at run time;
- accepts IOS-XE's own prompt as "running", and releases the console;
- never restarts a quiet VM.

`tests/test_configless_patch.py` checks each of these against the real
script, with three controls, each failing its target.

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
| P-M1 | Does the configless node start AutoInstall, PnP or ZTP? | Yes: with no startup config, IOS-XE 17.6 begins discovery on its own. The console shows PnP or AutoInstall messages, and/or DHCP requests leave the node |
| P-M2a | Is Gi1 answered? | Yes, by qemu's DHCP, within seconds. If AutoInstall runs, it may try TFTP against qemu's server on Gi1 and find nothing |
| P-M2b | Does a DHCPDISCOVER from `aa:bb:cc:00:02:50` appear on `br-mgmt`? | Yes, and it gets no offer (the MAC is unreserved on a pool-less subnet) |
| P-M2c | Does Gi1's answer stop discovery before Gi2 is tried? | Unknown. This is the measurement most likely to decide the lab |

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

Four hunks: the `-cdrom` guard, the watchdog, the console wait, and the
running branch. Then apply and confirm:

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
found"* and then the VM booting. The line that matters is
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

After 15 minutes, answer `no`, press RETURN, and record:

```text
show ip interface brief
show interfaces GigabitEthernet2 | include bia
show pnp summary
show logging | include PNP|DHCP|AUTOINSTALL|TFTP
```

`bia` must be `aabb.cc00.0250`. If it is not, that is the first finding, and
nothing about Kea may be concluded, exactly as in Phase 2.

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
| Gi1 answered, AutoInstall tried TFTP on Gi1, nothing on `br-mgmt` | Discovery is satisfied by qemu's network and never reaches the lab segment | Options are in section 9; stop and decide, do not improvise |
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
