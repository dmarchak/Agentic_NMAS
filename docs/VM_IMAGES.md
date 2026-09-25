# Nightly VM images on the Proxmox host (register B6)

Scoped 2026-09-25 from the operator's measurements. Nothing here has been
run yet. Every command runs **on the Proxmox host, as root**, and is the
operator's to run.

## What was measured, and the destination it picks

- **No vzdump job exists** (`/etc/pve/jobs.cfg` absent), so nothing images
  VM 100 or VM 102 (the NMAS VM: NetBox's postgres in Docker, `data/`,
  `/etc/kea`, Grafana).
- **All five VMs live on `vmdata`, the single NVMe.**
- **`pve/data` is a 348 G LVM-thin pool on `sda`, a separate SATA disk, and
  it is empty** (`Data% 0.00`). `local-lvm` maps to it and no VM uses it.
- **`local` (83 G) is the host's root filesystem.** Filling it takes the
  hypervisor down, so it is not a destination.

**The destination:** a 150 G volume from `pve/data`, formatted and added as a
`dir` storage for backups. It is on a different physical disk from the VMs,
has about 10x the space of `local`, and cannot fill `/`.

**What it covers and what it does not.** It survives a broken VM (a bad
upgrade, filesystem damage, a deleted directory) **and the NVMe dying**. It
does **not** survive losing the host. The images are also unencrypted and
each one holds `data/key.key` beside every ciphertext it opens. That is no
new exposure while they stay on the host, since root there can already read
the VM disks. They become a **copy that travels** the moment one leaves the
host, and must then be encrypted (CLAUDE.md, *Encryption at rest here
protects COPIES THAT TRAVEL*).

## 1. Create, format, mount, add the storage

```bash
# 0. Look first. Note VFree: if the VG has free space OUTSIDE the thin pool,
#    a thick LV (lvcreate -L 150G -n vzdump pve) avoids overcommitting the pool.
lsblk; pvs; vgs pve; lvs -a pve

# 1. A thin volume in the pool. Created by hand, so it is NOT flagged
#    activation-skip the way Proxmox flags guest volumes. Check that below.
lvcreate -V 150G -T pve/data -n vzdump
lvs -o lv_name,lv_size,lv_skip_activation pve/vzdump     # skip column must be empty

# 2. ext4 with no root reservation (nothing runs as root on a backup volume).
mkfs.ext4 -m 0 -L vzdump /dev/pve/vzdump

# 3. A persistent mount. `nofail` so a missing volume does not stop the boot;
#    `discard` so pruned images return their blocks to the thin pool.
mkdir -p /mnt/vzdump
echo '/dev/pve/vzdump /mnt/vzdump ext4 defaults,discard,nofail 0 2' >> /etc/fstab
systemctl daemon-reload
mount /mnt/vzdump && findmnt /mnt/vzdump

# 4. The Proxmox storage. `is_mountpoint yes` is the line that matters:
#    without it, a mount that failed at boot leaves /mnt/vzdump an ordinary
#    directory on the ROOT filesystem, and the night's images fill `/` --
#    exactly what choosing this disk was meant to prevent, arriving silently.
#    With it, the storage goes inactive and the job fails loudly instead.
pvesm add dir vzdump-sda --path /mnt/vzdump --content backup \
     --is_mountpoint yes --prune-backups keep-daily=3
pvesm status
```

**Negative control for `is_mountpoint`:** `umount /mnt/vzdump`, then
`pvesm status` must show `vzdump-sda` **inactive**. Then `mount /mnt/vzdump`.
A setting that was never seen refusing has not been shown to work.

## 2. Retention: what 150 G allows

Usable space is about 147 G (ext4 with `-m 0`). vzdump backs up the VMs **one
at a time** and prunes each VM **after** its new image is written. So the peak
is every kept image plus one new image in flight:

    peak = N x (size100 + size102) + max(size100, size102)

| Image size (each) | Most images kept per VM (N) | With 15% left for growth |
|---|---|---|
| 10 G | 6 | 5 |
| 12 G | 5 | 4 |
| 15 G | 4 | 3 |

**Start with `keep-daily=3`.** At 15 G per image that peaks at 105 G. After the
first run, measure the real sizes (`ls -l /mnt/vzdump/dump/`) and move to
`keep-daily=3,keep-weekly=1` only if each image is **13 G or smaller**. Four
per VM peaks at 9 x size, and 9 x 13 = 117 G leaves 20 % headroom.
~10–15 G is an estimate until then. An image holds the disk's **allocated**
blocks, and deleted files the guest has not trimmed still count, so an image
can be larger than `df` inside the VM suggests. That is why the first
measurement decides retention, not the estimate.

Retention is set once, on the storage. The job below sets none, so there is
one place to read it.

## 3. Snapshot mode with Docker and postgres on 102

`--mode snapshot` for a QEMU VM is QEMU's live backup: a point-in-time copy
of the disk **as of the moment the backup starts**. On its own that copy is
**crash-consistent**, the state a power cut at that instant would leave.

- **With the QEMU guest agent**, vzdump freezes the guest's filesystems
  (`fs-freeze`) for the instant the snapshot is taken and thaws them
  afterwards. That flushes the page cache and gives a **filesystem-consistent**
  image. It costs a pause of about a second. Recommended.
- **Postgres does not need more than that.** It is built to survive a crash:
  on start it replays its WAL and reaches a consistent state, provided
  `fsync` is on (the default) and the storage honours flushes (QEMU's default
  cache mode does). So a crash-consistent image of a running postgres is a
  power-loss recovery, not a corrupt backup. A backup that "restores and then
  doesn't work" comes from `fsync=off` or storage that lies about flushes.
  Neither applies here, and the restore test (section 5) turns that
  reasoning into a measurement.
- **NetBox's application-consistent copy is P.2's `pg_dump`,** hourly and
  restore-tested nightly. The image is the second line for NetBox and the
  first line for everything else on the VM.

```bash
qm config 102 | grep -i agent          # is it enabled on the VM?
qm agent 102 ping && echo agent-answers
# If not: inside the guest,  sudo apt-get install -y qemu-guest-agent
#         here,              qm set 102 --agent enabled=1
# then a FULL stop and start of the VM (not a reboot from inside): the
# virtio-serial device the agent talks over appears only at VM start.
```

**How you know it froze:** the vzdump task log for 102 contains
`issuing guest-agent 'fs-freeze' command` and `'fs-thaw'`. With no agent, the
log does not contain those lines. Read the log; don't assume either way.

## 4. The job

```bash
pvesh create /cluster/backup --id nmas-nightly --schedule '02:30' \
     --vmid 100,102 --storage vzdump-sda --mode snapshot --compress zstd \
     --enabled 1 --notes-template '{{guestname}}'
cat /etc/pve/jobs.cfg                  # now exists, naming the job

# The first run now, rather than tonight, so sizes and the freeze are measured:
vzdump 100 102 --storage vzdump-sda --mode snapshot --compress zstd
ls -l /mnt/vzdump/dump/
```

## 5. Test restore to a scratch VMID

**The restored VM must boot with its network down.** It is a second NMAS with
the same address and the same timers. With a live link it would SSH into the
lab (the drift schedule), push to the Proxmox backup user, write to NetBox
and poll Oxidized. `--unique 1` gives it new MACs, and `link_down=1` cuts
every interface.

```bash
qm list | grep -E '^ *910[02] ' && echo 'VMID TAKEN -- pick another'
qmrestore /mnt/vzdump/dump/vzdump-qemu-102-<timestamp>.vma.zst 9102 \
     --storage local-lvm --unique 1
qm config 9102 | grep ^net             # repeat the next line for EVERY netN
qm set 9102 --net0 <model>=<new-mac>,bridge=<bridge>,link_down=1
qm set 9102 --onboot 0
qm config 9102 | grep ^net             # every line must say link_down=1
qm start 9102                          # then log in on the web console
```

Inside the restored VM, it **passes** when:

1. postgres recovered: `docker logs <netbox postgres container> 2>&1 | grep -E 'not properly shut down|redo done|ready to accept'`
   shows recovery and then `ready to accept connections`. With an fs-freeze
   it may show a normal start instead; either is a pass, and a restart loop
   is a fail.
2. NetBox answers locally: `curl -s localhost:8000/api/status/` returns JSON.
3. The image carries the escrowed key. The network is down, so the record
   cannot be copied in; compare fingerprints instead. In the NMAS checkout:
   `python3 -c "import hashlib;print(hashlib.sha256(open('data/key.key','rb').read().strip()).hexdigest()[:16])"`
   must print the fingerprint `nmas-breakglass verify` printed on the laptop.
   (`key_fingerprint()` is that same computation.)
4. The app starts: `curl -s -o /dev/null -w '%{http_code}' localhost:5000/`
   prints 200.

Then `qm stop 9102 && qm destroy 9102 --purge`. VM 100 (the clab host) gets
the same restore with VMID 9100. Its pass is that `~/labs/*` are present and
`git -C ~/labs/lab log -1` answers. The labs themselves are rebuilt from
configs, so there is nothing to boot there.

The restore lands on `local-lvm`, the same thin pool as `vzdump`. That is
fine for a test that is destroyed straight afterwards. Check the pool's
`Data%` (`lvs pve/data`) before and after.

## 6. How a failed or filling job becomes visible (check 3)

**Pull, not push.** Proxmox's notification system can report a job that ran
and failed. It cannot report a job that **stopped running**: disabled,
deleted, a broken schedule, the host down at 02:30. That silence is C14's
shape, and it is why `job_health` judges each job by the **age of its last
success**, not by the absence of failure reports. So the check reads Proxmox
from NMAS, on the same terms as the systemd jobs.

**Read-only access** for NMAS, as a token with the auditor role and no
password login:

```bash
pveum user add nmas-monitor@pve --comment 'NMAS job_health, read-only'
pveum user token add nmas-monitor@pve job-health --privsep 1
pveum aclmod / -token 'nmas-monitor@pve!job-health' -role PVEAuditor
```

The token secret becomes a new encrypted setting (`secrets_store.SECRET_KEYS`),
and `nmas-check-secret-storage` classifies it with the rest.

**What NMAS would read, and the states it reports.** Proposed, not built.

| Source (Proxmox API) | State reported |
|---|---|
| `storage/vzdump-sda/content?content=backup`: newest image per VMID | per VM: `ok` if under 26 h old, `stale` otherwise, `never` if none exists |
| `tasks?typefilter=vzdump`: the latest task per VMID | `failing` with the task's own error line when the latest failed |
| `storage/vzdump-sda/status`: `active`, `avail` | `inactive` when the storage is not mounted (the `is_mountpoint` refusal made visible) |
| the same, against the newest image sizes | **`will_not_fit`** when `avail` < the largest image x 1.2 |
| `disks/lvmthin`: the pool's data and metadata use | `pool_filling` at 80 % of either |

**"Filling" is a question about the next run, not a percentage.** 85 % full
with 40 G free is fine when images are 12 G; 60 % full is not when an image
has grown to 60 G. `will_not_fit` asks whether tonight's largest image fits
beside what is kept, because vzdump prunes only **after** writing. It warns
the day before the failure. The thin pool is checked separately, because a
full thin pool fails writes for every volume in it, and a full **metadata**
area is the worse of the two.

It would surface wherever `job_health` does (`nmas-jobs`, the jobs route).
**Nothing there pushes an alert** — that is a limit of `job_health` as a
whole, not of this addition.

## Whether to send images to `vmdata` as well

**One destination on the right disk.** A second copy on `vmdata`:

- **adds no failure it covers.** The VMs already live there, so while
  `vmdata` is healthy the originals exist, and if it dies the copies die with
  them. Its only gain is depth of history, and depth is cheaper as a longer
  retention on `sda`.
- **puts backup growth on the disk the running VMs depend on.** If `vmdata`
  fills, the VMs on it pause or fail their writes. That is the same risk as
  filling `local`'s root filesystem, one level down, and it doubles the
  destinations `will_not_fit` has to watch.
- **Your two `vmdata` figures disagree.** 942 G at 85 % used leaves about
  141 G free, not 849 G. They are probably two different measures (thin-pool
  allocation against filesystem use). That needs settling
  (`pvesm status`, and `lvs` or `zfs list`) before `vmdata` is used for
  anything.

The gap neither disk closes is **off the host**. That is where depth belongs
next: Proxmox Backup Server with client-side encryption, or the images
through P.2's gpg-and-ship path.
