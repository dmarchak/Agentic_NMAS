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

**Custody as of 2026-09-25 (register B8):** the keyring and a restore-tested
`paperkey` file, both `0600`, on the laptop only; no printer for the paper
copy. The copies on the VM are plain, so losing the laptop alone loses no
data. Losing the laptop together with the Proxmox host leaves B2's copies
as the only ones, and nothing can read them. A second copy off this laptop
closes it. A password-manager entry counts only if it syncs somewhere else.

## 2. On the Proxmox host (10.0.0.80), as root

**Keep a second root session open until step 2d's test passes.** Step 2c
edits `sshd_config` on the hypervisor.

### 2a. Checks first

```bash
ls -l /usr/bin/rrsync                        # Debian 12 / PVE 8 ship it here, in the rsync package
ls -l /usr/share/doc/rsync/scripts/rrsync*   # older releases ship it gzipped here instead
df -h /srv /mnt/vzdump                       # where the two candidate destinations live
```

If `/usr/bin/rrsync` is absent and only the `.gz` exists, unpack it to
`/usr/local/bin/rrsync` (`gunzip -c`, then `chmod 755`) and use that path in
2b and 2c.

**Where the backups land.** The VM addresses `hourly/` and `daily/`
relative to rrsync's root, so the location is chosen here and nowhere else.
- `/srv/nmas-netbox` is on **pve-root**, the hypervisor's own root
  filesystem. At a few MB per file and about 41 kept, size is no concern.
  The risk is shape, not size: the account is write-only and cannot delete,
  so anything that writes in a loop fills `/`, and a full root filesystem
  takes the hypervisor down. That is the reason `local` was refused as B6's
  destination.
- `/mnt/vzdump/nmas-netbox` is on the `sda` volume B6 created, which cannot
  fill `/`. If that volume is not mounted, the subdirectories do not exist,
  so rrsync fails loudly and the backup's status goes stale. It fails
  closed. Its few hundred MB count against the images' free space, which
  `job_health`'s `will_not_fit` already reads.

Either works. The second cannot take the hypervisor down.

```bash
DEST=/mnt/vzdump/nmas-netbox          # or /srv/nmas-netbox
```

### 2b. The account, the directories, the key

```bash
useradd --system --create-home --home-dir /var/lib/nmas-backup --shell /bin/sh nmas-backup
passwd -S nmas-backup                 # second field must be L (locked): no password login exists
install -d -o nmas-backup -g nmas-backup -m 0700 "$DEST" "$DEST/hourly" "$DEST/daily"
install -d -o nmas-backup -g nmas-backup -m 0700 /var/lib/nmas-backup/.ssh

printf '%s\n' "command=\"/usr/bin/rrsync -wo $DEST\",restrict,from=\"10.0.0.211\" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeRwEfwUxS5t3mzWUk4MVP6SP6r/b3cS8FT9zU0zep8 nmas-netbox-backup@nmas" \
    > /var/lib/nmas-backup/.ssh/authorized_keys
chown nmas-backup:nmas-backup /var/lib/nmas-backup/.ssh/authorized_keys
chmod 0600 /var/lib/nmas-backup/.ssh/authorized_keys
cat /var/lib/nmas-backup/.ssh/authorized_keys     # the -wo path must show the real directory, not an empty $DEST
```

The key is the dedicated one on the VM (`~/.ssh/nmas_netbox_backup`),
checked 2026-09-25 to match the line above.

### 2c. The restriction in a second place: why the shell stays `/bin/sh`

**The shell cannot be `nologin`.** sshd runs a forced command through the
account's login shell (`$SHELL -c`, then the command). With
`/usr/sbin/nologin`, `nologin` receives the rrsync command, refuses it, and
every push fails. The restriction therefore cannot live in the shell. It
lives in three places that do not depend on each other:
1. **No password:** `passwd -S` shows the account locked, so the key is the
   only way in.
2. **The key's own options:** `command=` (rrsync, write-only, one
   directory), `restrict` (no pty, forwarding or agent) and `from=` (only
   the VM).
3. **sshd itself, for the account and not the key:** a `Match` block that
   forces the same command whatever `authorized_keys` says. So a second key
   added later without `command=` still gets rrsync and nothing else.

```bash
# At the END of the main file: a Match block runs until the next Match or
# end of file, so appended here it cannot capture anyone else's settings.
printf '\n%s\n' \
  "Match User nmas-backup" \
  "    ForceCommand /usr/bin/rrsync -wo $DEST" \
  "    AuthenticationMethods publickey" \
  "    PermitTTY no" \
  "    AllowTcpForwarding no" \
  "    AllowAgentForwarding no" \
  "    X11Forwarding no" \
  "    PermitTunnel no" >> /etc/ssh/sshd_config
tail -n 10 /etc/ssh/sshd_config       # the ForceCommand path must show the real directory
sshd -t && echo "config valid"        # reload ONLY if this prints "config valid"
systemctl reload ssh
# Measure the effective settings rather than trusting the file:
sshd -T -C user=nmas-backup,host=nmas,addr=10.0.0.211 | grep -Ei 'forcecommand|permittty|allowtcpforwarding'
sshd -T -C user=root,host=x,addr=10.0.0.211 | grep -i forcecommand   # must print "forcecommand none"
```

### 2d. Retention, and the test that passes step 2

```bash
# Retention is this side's job: rrsync -wo can write and cannot delete.
printf '%s\n' \
  "17 * * * * nmas-backup find $DEST/hourly -name '*.tar.gpg' -mmin +1560 -delete" \
  "23 3 * * * nmas-backup find $DEST/daily  -name '*.tar.gpg' -mtime +15  -delete" \
  > /etc/cron.d/nmas-netbox-retention
cat /etc/cron.d/nmas-netbox-retention # both paths must show the real directory, not "/hourly"
```

**Why `printf` and not heredocs:** every line above expands `$DEST`, and a
file written with an EMPTY `$DEST` is not an error. A cron line reading
`find /hourly ... -delete` would run every hour against the root filesystem.
So each write is followed by a `cat` or `tail` that shows the expanded path.

From the NMAS VM, once section 3 has put the host key in `known_hosts`:

```bash
ssh -i ~/.ssh/nmas_netbox_backup nmas-backup@10.0.0.80 true   # must be REFUSED by rrsync, not run
echo test > /tmp/probe.txt
rsync -e "ssh -i ~/.ssh/nmas_netbox_backup" /tmp/probe.txt nmas-backup@10.0.0.80:hourly/   # must succeed
rsync -e "ssh -i ~/.ssh/nmas_netbox_backup" nmas-backup@10.0.0.80:hourly/probe.txt /tmp/back.txt  # must be REFUSED (write-only)
```

Then, on Proxmox as root, remove the probe from `$DEST/hourly/`.

**The vzdump question is answered** (2026-09-25): there were no jobs on this
host. `nmas-nightly` now images VMs 100 and 102 at 02:30 to `vzdump-sda`
with `keep-daily=3`, a restore was tested, and `job_health` watches it (B6,
B7; docs/VM_IMAGES.md).

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
