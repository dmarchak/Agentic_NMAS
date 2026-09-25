# NetBox backup — install and operate (NSOT_PLAN P.2)

`scripts/nmas-netbox-backup` takes an hourly backup of NetBox (a `pg_dump` on
an exported snapshot, the media volumes, `env/` + `configuration/`, and a
manifest with per-table row counts on that same snapshot). It keeps hourlies
~26 h and dailies ~15 days on the NMAS VM, and ships gpg-encrypted copies:
every backup to the Proxmox host, dailies also off-box.
`scripts/nmas-netbox-restore-test` restores the newest one into a scratch
postgres and compares every table's row count with the manifest exactly.

**Measured 2026-09-25 on the VM**, from `/tmp` with a throwaway key:
- backup: 3.4 s; 198 tables, 3,142 rows; dump 1.29 MB; every file `0600`;
- encryption: decrypting with the key restores all 22 tar entries, and
  without it gpg refuses (`No secret key`);
- restore test: **PASS**, 198 tables and 3,142 rows identical, 18 s, scratch
  container removed.

The first live restore test **failed**, correctly: the count query was piped
to `docker exec` without `-i`, so every restored table came back `None`. The
mocked tests could not see it. `--status` also exited 0 beside that FAIL; a
failed or stale restore test now fails the status. Both are pinned.

## Why everything leaving the VM is encrypted

`env/netbox.env` carries `SECRET_KEY` and `API_TOKEN_PEPPER_1`, and a restore
without the pepper invalidates every v2 API token, so the configuration has
to travel with the dump. That is also why nothing goes to git. The VM holds
only the recipient's **public** key, so it cannot decrypt what it has
shipped, and a compromise of the VM does not expose the copies elsewhere.

## 1. Key custody: on a machine that is NOT the VM and NOT Proxmox

```bash
# on the laptop (or wherever the private key will live)
gpg --quick-gen-key "NMAS NetBox backup" default default never
FPR=$(gpg --list-keys --with-colons "NMAS NetBox backup" | awk -F: '/^fpr/{print $10; exit}')
gpg --armor --export "$FPR" > netbox-backup-recipient.asc          # public: goes to the VM
gpg --armor --export-secret-keys "$FPR" > netbox-backup-SECRET.asc # private: store it offline, twice
```

**Losing the private key makes every encrypted copy unrecoverable.** Keep a
second copy somewhere that is not the laptop either (a password manager or
printed with `paperkey`). Test a decrypt once shipping works (section 5).

## 2. On the Proxmox host (10.0.0.80), as root

```bash
apt-get install -y rsync                 # ships /usr/bin/rrsync on Debian 12+
command -v rrsync                        # must print a path; adjust below if not /usr/bin/rrsync

useradd --system --create-home --home-dir /var/lib/nmas-backup --shell /bin/sh nmas-backup
install -d -o nmas-backup -g nmas-backup -m 0700 /srv/nmas-netbox /srv/nmas-netbox/hourly /srv/nmas-netbox/daily
install -d -o nmas-backup -g nmas-backup -m 0700 /var/lib/nmas-backup/.ssh

cat > /var/lib/nmas-backup/.ssh/authorized_keys <<'EOF'
command="/usr/bin/rrsync -wo /srv/nmas-netbox",restrict,from="10.0.0.211" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeRwEfwUxS5t3mzWUk4MVP6SP6r/b3cS8FT9zU0zep8 nmas-netbox-backup@nmas
EOF
chown nmas-backup:nmas-backup /var/lib/nmas-backup/.ssh/authorized_keys
chmod 0600 /var/lib/nmas-backup/.ssh/authorized_keys

# Retention is the Proxmox side's job: rrsync -wo can write and cannot delete.
cat > /etc/cron.d/nmas-netbox-retention <<'EOF'
17 * * * * nmas-backup find /srv/nmas-netbox/hourly -name '*.tar.gpg' -mmin +1560 -delete
23 3 * * * nmas-backup find /srv/nmas-netbox/daily  -name '*.tar.gpg' -mtime +15  -delete
EOF
```

- **The key** is the dedicated one generated on the VM
  (`~/.ssh/nmas_netbox_backup`, `0600`). It does nothing but this.
- `restrict` disables forwarding, a pty and user rc files. `from=` pins it to
  the VM.
- `-wo` means write-only, so the VM cannot read back or delete what it sent.
- **`/srv/nmas-netbox` is an example path.** If a Proxmox storage should hold
  it (for example `/mnt/pve/<storage>/nmas-netbox`), use that path in all
  three places.
- **Put it outside the NMAS VM's own disk** so that losing the VM does not
  take the backups with it.

**Check the vzdump schedule while you are there** (not answerable from inside
the VM, because the schedule lives on this host):

```bash
qm list | grep -i nmas                    # the NMAS VM's VMID
cat /etc/pve/jobs.cfg                     # scheduled backup jobs: vmid list / "all" / pool
pvesh get /cluster/backup --output-format json-pretty
```

## 3. On the NMAS VM

```bash
# trust the Proxmox host key once, after checking its fingerprint on the console
ssh-keyscan -t ed25519 10.0.0.80 | tee -a ~/.ssh/known_hosts
ssh-keygen -lf <(ssh-keyscan -t ed25519 10.0.0.80 2>/dev/null)   # compare with: ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub on Proxmox

sudo install -d -m 0750 -o root -g dmarchak /etc/nmas
sudo install -m 0644 -o root -g dmarchak netbox-backup-recipient.asc /etc/nmas/netbox-backup-recipient.asc
sudo install -m 0640 -o root -g dmarchak deploy/systemd/netbox-backup.env.example /etc/nmas/netbox-backup.env
sudoedit /etc/nmas/netbox-backup.env      # set NMAS_BACKUP_RCLONE_REMOTE when off-box is ready

sudo install -m 0644 deploy/systemd/nmas-netbox-backup.service deploy/systemd/nmas-netbox-backup.timer \
     deploy/systemd/nmas-netbox-restore-test.service deploy/systemd/nmas-netbox-restore-test.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start nmas-netbox-backup.service && journalctl -u nmas-netbox-backup -n 20 --no-pager
sudo systemctl start nmas-netbox-restore-test.service && journalctl -u nmas-netbox-restore-test -n 5 --no-pager
sudo systemctl enable --now nmas-netbox-backup.timer nmas-netbox-restore-test.timer
```

These are system units running as `dmarchak` with `docker` as a
supplementary group, so no linger is needed. `StateDirectory=nmas-netbox`
creates `/var/lib/nmas-netbox` (`0700`, owned by the service user).

## 4. Off-box (dailies only)

```bash
sudo apt-get install -y rclone
rclone config                            # as dmarchak: create a remote, e.g. "offbox"
# then in /etc/nmas/netbox-backup.env:
NMAS_BACKUP_RCLONE_REMOTE=offbox:nmas-netbox
```

Only a newly promoted daily is sent. **Backblaze B2, decided 2026-09-25: the
key is write-and-list only, and retention is the bucket's.**
- A lifecycle rule on the bucket keeps files 15 days.
- The application key is restricted to that bucket, with `listBuckets`,
  `listFiles` and `writeFiles`, and **no `deleteFiles`**.
- A VM that can delete its own backups is protected against disk failure
  and not against compromise, which is the case backups exist for. The
  Proxmox copy is write-only for the same reason (`rrsync -wo`).
- `NMAS_BACKUP_OFFBOX_PRUNE` stays `0`, so the script never tries to delete,
  and `--status` says retention is the bucket's.
- **The B2 key lives in `~/.config/rclone/rclone.conf`**, a secret store
  that `nmas-check-secret-storage` checks by path (`0600`).

## 5. Status, and proving a copy decrypts

```bash
NMAS_BACKUP_ROOT=/var/lib/nmas-netbox NMAS_BACKUP_GPG_RECIPIENT_FILE=/etc/nmas/netbox-backup-recipient.asc \
  NMAS_BACKUP_PROXMOX_TARGET=nmas-backup@10.0.0.80 NMAS_BACKUP_RCLONE_REMOTE=offbox:nmas-netbox \
  scripts/nmas-netbox-backup --status        # 0 fresh, 1 stale/failed, 2 never ran
```

**An unconfigured destination is reported by name, never as a success**, and
a failed or stale (>50 h) restore test fails the status.

To prove an off-VM copy is usable, fetch one `.tar.gpg` to the machine that
holds the private key and run `gpg -d <file> | tar -tf -`. The listing must
include `netbox.pgdump`, `manifest.json` and `config/env/netbox.env`.

## What this does not give

- **Point-in-time recovery.** Up to an hour of hand edits to NetBox between
  dumps is lost. NMAS's own writes are also in the modification record and
  the goldens.
- **An application-level restore.** The restore test proves the database, not
  that NetBox boots on it with the backed-up pepper. Booting a scratch
  NetBox on the restored data is the next step if that assurance is wanted.
- **Retrying a failed ship.** A failed push is recorded and the next hour's
  backup is shipped instead; the status goes stale if pushes keep failing.
