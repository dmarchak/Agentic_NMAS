# Phase 2 probe — a management address delivered by DHCP

**Subject: `bp-dhcp-a`, a throwaway.** Why not r6:
[PHASE2_DHCP.md](PHASE2_DHCP.md) §1–2. Topology:
`docs/bootstrap-probe/nmas-dhcp-a.clab.yml`.

Same pattern as `STAGE4C_PROBE.md` — own lab name, own containerlab network,
own launch-patch copy, `br-mgmt`, a temporary list, teardown at the end. Every
**action** through the GUI; the shell only **measures**.

---

## ⚠ Two things are unverified, and both must be settled before any conclusion

### 1. The pinned MAC may not be what the DHCP client presents

`nmas-dhcp-a.clab.yml` pins `aa:bb:cc:00:02:40` on the veth, and Kea reserves
`10.255.0.40` for it. **vrnetlab runs a VM behind the container**, and the MAC
`GigabitEthernet2` presents inside the VM may be assigned by vrnetlab rather
than taken from the container's interface. Nothing in this repository has
measured which.

**Step 7 checks it on the booted node, before anything is concluded about
Kea.** A MAC mismatch produces silence on the wire, and silence looks exactly
like a Kea problem — which is the expensive way to spend an evening.

If it does not match: that **is** the finding. Read the real MAC, put it in the
reservation, reload, redeploy. The node's first boot is then unaddressed —
acceptable **only because this node is disposable**, and a finding for the
production story rather than a detail of this probe.

### 2. Nothing has ever answered a DHCPDISCOVER on `10.255.0.0/24`

The subnet was added on 2026-09-24 with reservations and **no pool**. Before
that Kea served only the two relay-reached subnets, and there were **zero
reservations anywhere**. So:

* the **read** path is proven — `reservation_for('aa:bb:cc:00:02:40')` returns
  `reserved / 10.255.0.40`, and the reload now works through the tool;
* the **answer** path is not. A failure can be the code, the config, or the
  segment, and **step 8 separates them before anyone edits anything.**

---

## Step 0a — ⛔ the census baseline, BEFORE anything can write

Not step 2, and not later. There is **exactly one truthful moment** and it is
before the first step that can create a NetBox object; a baseline taken
afterwards contains the probe's own objects, and the teardown would then
measure clean while leaving them behind — worse than having no baseline.

```bash
python3 scripts/nmas-netbox-census --out /tmp/census-dhcp-a.json
test -s /tmp/census-dhcp-a.json && echo "BASELINE TAKEN"
```

An empty baseline (`{"types": {}}`) is refused by `--compare` for the same
reason: every comparison against it passes.

## Step 0b — confirm the posture survived the reload

**The reservations-only posture is the point, not an accident of the probe.**

```bash
sudo kea-shell --service dhcp4 config-get 2>/dev/null \
  | python3 -c 'import json,sys; \
      s=[x for x in json.load(sys.stdin)[0]["arguments"]["Dhcp4"]["subnet4"] \
         if x["subnet"]=="10.255.0.0/24"][0]; \
      print("pools:", s.get("pools", "NONE")); \
      print("reservations:", len(s.get("reservations", []))); \
      print("id:", s.get("id"))'
```

- [ ] `pools: NONE` — if a pool has appeared, stop. Dynamic addressing on the
      segment carrying the NMAS, s3's SVI and r6 is worse than no DHCP at all
- [ ] one reservation, and the other two subnets' **ids are unchanged** (Kea
      keys leases by id; a renumber orphans them)

## Step 0c — the regression check that must still hold afterwards

r6 is untouched by this probe and its acceptance is the guard that says so:

```
r1# show ip route 10.255.1.16
```

- [ ] `extern 2`, metric `20`, from `10.255.1.23` — **recorded now**, and
      re-checked at step 12

## Step 1 — a temporary list, not `default`

Through the GUI. The onboarding target list is **carried, never derived**, and
onboarding into the wrong list leaves a commit, a NetBox object and a CSV row
in a live network.

## Step 2 — enable NetBox writes, deliberately

`netbox_allow_writes` is off by default and is a persistent operator decision.
Turn it on knowingly; step 12 turns it back off.

## Step 3 — prepare the clab host (no node is booted here)

### 3a. Stage the launch patch — the probe's **own** copy

```bash
ssh <clab> 'mkdir -p ~/labs/dhcp-a/patches ~/labs/dhcp-a/configs && \
  cp ~/labs/lab/patches/c8000v-launch.py \
     ~/labs/dhcp-a/patches/c8000v-launch-adopted.py && \
  grep -c "smp" ~/labs/dhcp-a/patches/c8000v-launch-adopted.py'
```

Never bind `~/labs/lab/patches/` — a throwaway lab whose teardown can reach
into production is not throwaway. `-adopted` because `c8000v-launch.py` in
that directory deliberately **predates** the user-skip and is what makes
`nmas-bootstrap-probe.clab.yml` reproduce the hazard.

### 3a2. Confirm the containerlab subnet is free

The probe declares `clab-dhcp-probe` on **172.30.60.0/24**. Its first choice,
`172.30.50.0/24`, collided with `clab-r6` — running now, and a file on the clab
host rather than in this repository, so nothing in the repo could have known.

```bash
ssh <clab> 'docker network ls --format "{{.Name}}" | while read n; do \
  printf "%-26s %s\n" "$n" "$(docker network inspect -f "{{range .IPAM.Config}}{{.Subnet}}{{end}}" "$n")"; done'
```

- [ ] nothing holds `172.30.60.0/24`
- [ ] if something does, pick another **and add the occupied one to
      `RESERVED_MGMT_SUBNETS` in `tests/test_probe_topologies.py`** — that list
      is the only way the repository can know, and the next probe will make the
      same mistake otherwise

### 3b. Confirm `br-mgmt` and see who is on it

```bash
ssh <clab> 'ip -br link show master br-mgmt'
```

- [ ] the host uplink, `s3-mgmt`, r6's veth — and **no `dhcpa-mgmt`**

### 3c. Confirm `10.255.0.40` is free, three ways

NetBox holds nothing on it · no ping reply · the neighbour table shows it
`INCOMPLETE`. The convention `.31` and `.32` both used.

## Step 4 — the wizard, with `address_source: dhcp`

Through the GUI. Hostname `bp-dhcp-a`, platform `cisco_iosxe`, manager
interface `Gi2`, **MAC `aa:bb:cc:00:02:40`**, address source **dhcp**.

- [ ] the review screen reads
      **`assigned by Kea reservation aa:bb:cc:00:02:40 → 10.255.0.40`** — a
      claim checked a moment ago, not a promise about later
- [ ] Create succeeds, and the pending banner lists the device

**If the review says `no reservation` or `could not be asked`, the plan
refuses** — that is the precondition working, and the fix is Kea's config or
credentials, not the wizard.

## Step 5 — write the artefact and deploy

```bash
# The bootstrap config the wizard produced, re-derived from committed intent
curl -s localhost:5000/onboard/bootstrap/bp-dhcp-a   # a REVEAL: person-gated
```

- [ ] it contains **` ip address dhcp`** on `GigabitEthernet2`, and **no**
      static address
- [ ] write it to `~/labs/dhcp-a/configs/bp-dhcp-a.cfg`, then
      `containerlab deploy -t nmas-dhcp-a.clab.yml`

## Step 6 — the boot

- [ ] `Startup complete` (~6m30s)
- [ ] **no `%CVAC-4-CLI_FAILURE`** for a username line — the user-skip fired
- [ ] the running config shows `secret 9`, not `password 0`

## Step 7 — ⚠ the MAC check, BEFORE any conclusion about Kea

On the node's console (`docker exec -it clab-nmas-dhcp-a-bp-dhcp-a telnet localhost 5000`):

```
show interface GigabitEthernet2 | include bia
```

- [ ] it matches `aa:bb:cc:00:02:40`

**If it does not, stop and record it.** Everything downstream would fail for
this reason and blame Kea. Fallback: reserve the real MAC, reload, redeploy.

## Step 8 — did it get the address, and if not, which layer

- [ ] `show ip interface brief | include GigabitEthernet2` → `10.255.0.40`

If not, separate the three candidates **before editing anything**:

| question | command | what it tells you |
|---|---|---|
| did the client ask? | `debug ip dhcp client packet` on the node | silence here is the device, not the network |
| did Kea hear it? | `sudo journalctl -u kea-dhcp4 -n 50` on the Kea host | a DHCPDISCOVER logged with no offer is the config |
| did the segment carry it? | `sudo tcpdump -i enp6s19 -n port 67 or port 68` | nothing at all is the wire |
| does Kea hold a lease? | Monitoring panel, or `lease4-get-all` | a lease Kea granted and the device does not hold is the segment |

## Step 9 — phase 2 of onboarding, against a DHCP address

Verify from the pending banner. Seven steps: verify → capture → rotate →
remove RW → golden → NetBox → promote.

- [ ] all seven report, and **promotion is last**
- [ ] the CSV row carries `10.255.0.40` and the **rotated** credential
- [ ] the address the tool recorded **is the lease Kea issued** — checked
      against Kea, not against the device's own claim
- [ ] the first golden contains **no** `snmp-server … RW` line

## Step 10 — the record agrees with Kea

```bash
python3 -c "
from modules.integrations.kea import KeaIntegration
print(KeaIntegration().reservation_for('aa:bb:cc:00:02:40'))"
```

- [ ] `reserved / 10.255.0.40`, and the manifest, the CSV and NetBox all say
      `10.255.0.40`. Four stores, one answer

## Step 11 — reboot-safety is NOT claimed

This node is not in `clab_labs`, so the persistence chain does not know it and
a clab-host reboot brings it back on its bootstrap config. **Stated, not
fixed** — it is a throwaway and it is being destroyed at step 12. The same gap
on r6 got a deadline because r6 is permanent.

## Step 12 — teardown, and the census must prove it

```bash
test -s /tmp/census-dhcp-a.json || { echo "NO BASELINE — do not Remove"; exit 2; }
ssh <clab> 'cd ~/labs/dhcp-a && containerlab destroy -t nmas-dhcp-a.clab.yml --cleanup'
```

- [ ] the baseline file exists **before** the Remove, not at the `--compare`
      when the objects are already gone
- [ ] NetBox Remove through the GUI — provenance governs, and the cascade
      preview names every foreign object
- [ ] `nmas-netbox-census --compare /tmp/census-dhcp-a.json` → **exit 0**.
      Exit 1 is *"objects left behind"*; **exit 2 is UNPROVEN** and is not a pass
- [ ] delete the temporary list; turn `netbox_allow_writes` back off
- [ ] `br-mgmt` holds no `dhcpa-mgmt`, and `--cleanup` disturbed neither the
      bridge nor r6
- [ ] **step 0c again**: `r1` still learns `10.255.1.16` as extern 2, metric
      20, from `10.255.1.23`
- [ ] `10.255.0.0/24` still has **no pool**; remove the probe's reservation

## If a step fails

Stop and measure. Do not redeploy to "try it clean" — a second deploy destroys
the evidence of why the first failed. The console and the break-glass record
are the way in, and on this node the cheapest recovery is
`containerlab destroy`.
