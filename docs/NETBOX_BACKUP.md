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
( set -eu
  : "${DEST:?set DEST first, see 2a}"
  useradd --system --create-home --home-dir /var/lib/nmas-backup --shell /bin/sh nmas-backup
  passwd -S nmas-backup                 # second field must be L (locked): no password login exists
  install -d -o nmas-backup -g nmas-backup -m 0700 "$DEST" "$DEST/hourly" "$DEST/daily"
  install -d -o nmas-backup -g nmas-backup -m 0700 /var/lib/nmas-backup/.ssh

  printf '%s\n' "command=\"/usr/bin/rrsync -wo $DEST\",restrict,from=\"10.0.0.211\" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeRwEfwUxS5t3mzWUk4MVP6SP6r/b3cS8FT9zU0zep8 nmas-netbox-backup@nmas" \
      > /var/lib/nmas-backup/.ssh/authorized_keys
  chown nmas-backup:nmas-backup /var/lib/nmas-backup/.ssh/authorized_keys
  chmod 0600 /var/lib/nmas-backup/.ssh/authorized_keys
  cat /var/lib/nmas-backup/.ssh/authorized_keys     # the -wo path must show the real directory, not an empty $DEST
)
```

The key is the dedicated one on the VM (`~/.ssh/nmas_netbox_backup`),
checked 2026-09-25 to match the line above.

### 2c. The restriction in a second place: why the shell stays `/bin/sh`

**The shell cannot be `nologin`.** sshd(8)/sshd_config(5): a forced command
"is invoked by using the user's login shell with the -c option". With
`/usr/sbin/nologin`, `nologin` receives the rrsync command, refuses it, and
every push fails. So the restriction cannot live in the shell. It lives here:
1. **No password:** `passwd -S` shows the account locked, so the key is the
   only way in.
2. **The key's non-command options, which apply alongside everything else:**
   `restrict` (no pty, forwarding or agent) and `from=` (only the VM).
3. **The forced command, set in TWO places, and they are NOT two layers.**
   When both are set, sshd runs the config's `ForceCommand` and ignores the
   key's `command=`. sshd(8): the key's command "may be superseded by a
   sshd_config(5) ForceCommand directive". At any moment **exactly one
   command is in force**, so this is not belt and braces. What the pair buys
   is two independent ways to LOSE the restriction, each covered by the
   other:
   - the `Match` block covers a key added later **without** `command=`;
   - the key's `command=` covers the `Match` block being lost (a package
     upgrade that replaces `sshd_config`, an edit, a reset).
   **So the two must name the same command.** A difference changes nothing
   while both stand, and silently changes what the account can do on the
   day one goes. And the key's `command=` is inert while the `Match` block
   stands, so no test can show it working. To test it deliberately, comment
   out the `Match` block, reload, re-run 2d's three tests, and restore.

**rrsync works under either.** It reads the client's rsync request from
`SSH_ORIGINAL_COMMAND`, which sshd sets for both kinds of forced command
("the command originally supplied by the client is available in the
SSH_ORIGINAL_COMMAND environment variable"). It takes the directory and
`-wo` from its own arguments, and exits with "Not invoked via sshd" without
the variable (read in rrsync 3.4.1's source; Debian's 3.2.x has the same
design). So `ForceCommand` does not break the push. 2d's tests are the
measurement.

```bash
( set -eu
  : "${DEST:?set DEST first, see 2a}"
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
  sshd -t                             # an invalid config stops the block HERE, before the reload
  systemctl reload ssh
  # Measure the effective settings rather than trusting the file:
  sshd -T -C user=nmas-backup,host=nmas,addr=10.0.0.211 | grep -Ei 'forcecommand|permittty|allowtcpforwarding'
  sshd -T -C user=root,host=x,addr=10.0.0.211 | grep -i forcecommand   # must print "forcecommand none"
)
```

### 2d. Retention, and the test that passes step 2

```bash
( set -eu
  : "${DEST:?set DEST first, see 2a}"
  # Retention is this side's job: rrsync -wo can write and cannot delete.
  printf '%s\n' \
    "17 * * * * nmas-backup find $DEST/hourly -name '*.tar.gpg' -mmin +1560 -delete" \
    "23 3 * * * nmas-backup find $DEST/daily  -name '*.tar.gpg' -mtime +15  -delete" \
    > /etc/cron.d/nmas-netbox-retention
  cat /etc/cron.d/nmas-netbox-retention # both paths must show the real directory, not "/hourly"
)
```

**Why `printf` and not heredocs:** every line above expands `$DEST`, and a
file written with an EMPTY `$DEST` is not an error. A cron line reading
`find /hourly ... -delete` would run every hour against the root filesystem.
So each write is followed by a `cat` or `tail` that shows the expanded path.

**Why each block is one `( set -eu … )` unit:** pasted into an interactive
shell, a failing line stops only itself and the next lines run anyway, so
a guard at the top of a pasted block guards nothing. Inside the subshell,
the first failure ends the block: an unset `$DEST`, a user that already
exists, or `sshd -t` rejecting the config. If 2c stops at `sshd -t`, the
file on disk is invalid but NOT loaded. Fix it before anything restarts
sshd, with the second root session still open.

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

**Pull first.** The unit runs the script from the checkout, and the off-box
push needs the `--no-check-dest` change (2026-09-25).

```bash
# 3a. The Proxmox host key: VERIFY, then trust. Compare this fingerprint with
#     `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` run on the Proxmox console.
ssh-keygen -lf <(ssh-keyscan -t ed25519 10.0.0.80 2>/dev/null)
# only if they match:
ssh-keyscan -t ed25519 10.0.0.80 >> ~/.ssh/known_hosts
```

```bash
# 3b. The recipient's PUBLIC key, copied from the laptop to ~/ on this host
#     (scp netbox-backup-recipient.asc dmarchak@10.0.0.211:~/). Every path is
#     absolute, so this does not depend on the directory it is run from.
( set -eu
  cd ~/python/Agentic_NMAS
  sudo install -d -m 0750 -o root -g dmarchak /etc/nmas
  sudo install -m 0644 -o root -g dmarchak ~/netbox-backup-recipient.asc /etc/nmas/netbox-backup-recipient.asc
  gpg --show-keys --with-fingerprint /etc/nmas/netbox-backup-recipient.asc   # must equal the laptop's fingerprint
  # The env file is installed ONCE: re-running this must not overwrite an edited one.
  if [ -e /etc/nmas/netbox-backup.env ]; then
    echo "env exists, left as it is"
  else
    sudo install -m 0640 -o root -g dmarchak deploy/systemd/netbox-backup.env.example /etc/nmas/netbox-backup.env
  fi
)
sudoedit /etc/nmas/netbox-backup.env      # set NMAS_BACKUP_RCLONE_REMOTE (section 4); check RCLONE_CONFIG
sudo grep -v '^#' /etc/nmas/netbox-backup.env | grep .     # show what the unit will read
```

```bash
# 3c. The units, one run of each by hand, then the timers.
( set -eu
  cd ~/python/Agentic_NMAS
  sudo install -m 0644 deploy/systemd/nmas-netbox-backup.service deploy/systemd/nmas-netbox-backup.timer \
       deploy/systemd/nmas-netbox-restore-test.service deploy/systemd/nmas-netbox-restore-test.timer /etc/systemd/system/
  sudo systemctl daemon-reload
)
sudo systemctl start nmas-netbox-backup.service; journalctl -u nmas-netbox-backup -n 20 --no-pager
sudo systemctl start nmas-netbox-restore-test.service; journalctl -u nmas-netbox-restore-test -n 5 --no-pager
# Enable the timers only after both runs above read as they should:
sudo systemctl enable --now nmas-netbox-backup.timer nmas-netbox-restore-test.timer
~/python/Agentic_NMAS/scripts/nmas-jobs    # nmas-netbox-backup and -restore-test ok; not "not_installed"
```

The two `start` lines are deliberately NOT chained with `&&`. A failed run
must still show its journal, because the journal is where its reason is.

These are system units running as `dmarchak` with `docker` as a
supplementary group, so no linger is needed. `StateDirectory=nmas-netbox`
creates `/var/lib/nmas-netbox` (`0700`, owned by the service user).
`RCLONE_CONFIG` in the env file points rclone at the B2 key's config
explicitly, rather than relying on systemd setting `$HOME`.

## 4. Off-box (dailies only)

**Set up 2026-09-25:** bucket `nmas-netbox-dmarchak`; lifecycle keeps a file
15 days, then hides it, and deletes a hidden version 1 day later. The
application key is restricted to that bucket with `listBuckets`,
`listFiles` and `writeFiles`, and **no `deleteFiles` and no `readFiles`**.
Only a newly promoted daily is sent.

In `/etc/nmas/netbox-backup.env`:
```
NMAS_BACKUP_RCLONE_REMOTE=<remote-name>:nmas-netbox-dmarchak
RCLONE_CONFIG=/home/dmarchak/.config/rclone/rclone.conf
NMAS_BACKUP_OFFBOX_PRUNE=0
```

- **The push needs `--no-check-dest`, and the script always passes it.**
  By default rclone first reads the destination (a HEAD request) to decide
  whether to copy, and that needs `readFiles`. Measured: without it the copy
  fails with 401. A 401 or 403 is reported as the key being REFUSED, with
  the capabilities it needs, rather than as rclone's raw text.
- **The B2 key lives in `~/.config/rclone/rclone.conf`**, in plaintext
  (rclone obscures, it does not encrypt). `nmas-check-secret-storage`
  checks it by path: `0600`, measured.

### What the key can and cannot do: measure it, with a test that can fail

**Neither the exit code nor a listing after a deletion is evidence by
itself.** Measured 2026-09-25: `rclone delete <remote>:<bucket>/b2probe.txt`
exited 0, and the file was still listed. Two readings produce exactly that
output:
1. The deletion was attempted and refused.
2. **The deletion was never attempted.** To use a single-file path, rclone
   first checks that the path is a file, by the same HEAD request that
   needs `readFiles`. Refused, it treats `b2probe.txt` as a *directory*,
   finds nothing in it, deletes nothing, and exits 0. This is the same
   refusal that made the default copy fail.

A test that passes in both cases proves nothing. And the property that
matters is not quite deletion. **On B2, rclone's delete HIDES a file by
default** (unless given `--b2-hard-delete`). Per B2's documentation as
understood here, hiding needs only `writeFiles`, which this key has. **The
lifecycle deletes a hidden version 1 day later.** If both hold, a
compromised VM can erase every off-box copy within a day, with no
`deleteFiles` at all (register **B9**).

The test that decides it points rclone at the bucket, which needs only
`listFiles`, and selects the probe with a filter, so a deletion is actually
attempted:

```bash
rclone lsl <remote>:nmas-netbox-dmarchak --b2-versions            # BEFORE: note b2probe.txt
rclone delete -vv <remote>:nmas-netbox-dmarchak --include b2probe.txt 2>&1 | tail -20
rclone lsl <remote>:nmas-netbox-dmarchak                          # the current view
rclone lsl <remote>:nmas-netbox-dmarchak --b2-versions            # every version, hidden ones included
```

Read the `-vv` output first. It says what rclone attempted and what B2
answered.
- **Refused** (an error naming the capability, a non-zero exit, and the
  file still in the current view): the key cannot hide. The off-box copy is
  protected against a compromised VM, and B9 closes.
- **Hidden** (a line saying the file was deleted or hidden, gone from the
  current view, present among the versions): the key CAN destroy the
  off-box copy within a day. The fix is **B2 Object Lock** with a default
  retention at least as long as the lifecycle's whole window (16 days). A hide is then
  still possible, but no version can be deleted until its retention
  expires, by the lifecycle or by anyone. The lifecycle's 1-day
  hide-to-delete is the window an attacker would use, and lengthening it
  only widens the window to notice.

Only the probe file is touched either way. It was written to be disposable.

### MEASURED 2026-09-26: the key CAN hide, so without a lock it can destroy the off-box copies

The discriminating test above, run by the operator:
- `rclone delete -vv --include b2probe.txt` printed `INFO : b2probe.txt: Deleted`, with no refusal anywhere;
- the normal listing was **empty**;
- `--b2-versions` listed `b2probe-v2026-09-26-020544-483.txt`, 27 bytes.

**The write-only key hid the file using only `writeFiles`.** The lifecycle
deletes a hidden version 1 day later, so a compromised NMAS erases every
off-box copy within 24 hours. **Withholding `deleteFiles` bought nothing.**
The earlier test (a single-file path: exit 0, file still listed) passed
because the file was never touched.

### The fix: Object Lock, Governance mode, a default retention covering the lifecycle's whole window (16 days)

B2's semantics as understood here, **to be measured on probes before real
data depends on them** (the plan below):
- **Governance, not Compliance.** Against a compromised VM they protect
  equally, because the NMAS key has no `bypassGovernance`. Governance leaves
  the account owner an escape hatch (a key with `bypassGovernance`, which
  the master key is believed to have) for a mistake such as a retention of
  15 *years*. Compliance cannot be undone by anyone, and protects against a
  stolen B2 login, which is not this threat.
- **Enabling Object Lock on the bucket is one-way.** The default retention
  can be changed or removed later, and it applies only to NEW uploads.
- **A lock stops deletion, not hiding.** After an attack, every file may be
  hidden. The locked versions remain, recoverable with the account's own key
  until their retention expires.
- **What a lock cannot stop is filling.** Anything written with
  `writeFiles` is locked for 16 days, including garbage from a compromised
  VM or a bug. Guard it with a B2 storage cap on the account, and
  Governance's bypass for cleaning up.
- **The property: lock retention >= the lifecycle's hide-after PLUS its
  hide-to-delete (15 + 1 = 16 days).** A daily's natural life under the
  lifecycle is 16 days: hidden at 15, deleted at 16. With a 16-day lock,
  **no hide, at any moment, deletes anything sooner than the lifecycle
  would have**, so an attack cannot shorten any file's life. (This first
  said "retention = 15 days, equal to the hide-after". That was wrong by
  the hide-to-delete day: at 15 the lock expires a day before the
  lifecycle's deletion, so a file hidden on its last day went a day early.
  The operator's property caught it, 2026-09-26.) **Shorter** re-opens the
  hole for every file older than the lock. **Longer** defers the
  lifecycle's deletions until the lock expires, so the lock silently
  becomes the retention: two owners of one decision. As understood here,
  B2's lifecycle neither errors nor reports when it meets a locked
  version; it deletes the version on a later daily run once the lock has
  expired. **So a check fails on shorter, warns on longer, and passes at
  exactly equal** (register B10).

**Measurement plan, probes only:**
1. The hidden, unlocked `b2probe` version should be GONE from
   `--b2-versions` about a day after it was hidden. That proves the
   lifecycle runs, and it is the positive control for step 4.
2. Enable Object Lock with a default retention of Governance, 16 days.
   Upload a new probe with the NMAS key (`copyto --no-check-dest`) and check
   its retention in the B2 web UI.
3. With the NMAS key, hide it (`delete -vv --include`). Expected: hidden,
   with the locked version still present in `--b2-versions`.
4. A day later, the hidden LOCKED version should still be there. That is
   the direct measurement of what the lifecycle does under a lock.
5. With the master key, delete the probe, bypassing governance. That proves
   a mistake can be undone.

**Not yet possible: checking that the two windows agree.** Reading the
bucket's lifecycle rules and default retention would let `--status` refuse a
mismatch. That needs capabilities this key lacks (`readBucketRetentions`), and
B2 key capabilities cannot be edited, only issued anew (register B10).

## 5. Status, and what steps 5 and 6 measured

```bash
NMAS_BACKUP_ROOT=/var/lib/nmas-netbox NMAS_BACKUP_GPG_RECIPIENT_FILE=/etc/nmas/netbox-backup-recipient.asc \
  NMAS_BACKUP_PROXMOX_TARGET=nmas-backup@10.0.0.80 NMAS_BACKUP_RCLONE_REMOTE=b2:nmas-netbox-dmarchak \
  scripts/nmas-netbox-backup --status        # 0 fresh, 1 stale/failed, 2 never ran
```

**An unconfigured destination is reported by name, never as a success**, and
a failed or stale (>50 h) restore test fails the status.

**Measured 2026-09-26 (operator), steps 5 and 6:**
- Three destinations, all 363,799 bytes: local (an unencrypted directory),
  Proxmox (`.tar.gpg`), and B2 (`.tar.gpg`).
- The Proxmox copy is encrypted to ECDH key `1FDBB1E129FA3C99`, the cv25519
  subkey of the laptop keypair, and the NMAS **cannot** decrypt it
  (`No secret key`), as intended.
- Local contents: `netbox.pgdump` (1.3 MB), `media.tar`, `config/`,
  `manifest.json`.
- Restore test **PASS**: 198 tables and 3,143 rows identical, in 20 s.

**Every off-box push is confirmed by LISTING, not by rclone's exit code.**
Measured: a refused read was retried ten times (`401`), then rclone printed
`There was nothing to transfer` and exited **0**. The 401 was visible only
at `-vv`. So after `copyto`, the script lists `daily/` and requires the
object at the artefact's exact size. It lists the DIRECTORY, because a
single-file path makes rclone HEAD the object, which needs `readFiles`. A
prune, when enabled, is confirmed the same way.

## 6. Retrieving an off-box copy (step 7)

**Decided 2026-09-26: one READ-ONLY B2 key, kept on the laptop for
retrieval and on the NMAS for the lock/lifecycle check (B10).** Until it
exists, **no credential on any machine can read the off-box copies**: the
write key has no `readFiles`, by design, and the laptop has no rclone. A
restore whose first step is "log in to a web console and create a
credential" fails when it is needed most.

Why the read key may also live on the NMAS: everything it can read, the
NMAS already holds UNENCRYPTED (the live database, and the plain local
copies under `/var/lib/nmas-netbox`). A read key there exposes ciphertext of
data the host already has in the clear, and it lets the NMAS check its own
off-box copies. It cannot write, hide or delete, so it cannot undermine what
it checks.

### 6a. The key (B2 web UI, once)

App Keys, then Add a New Application Key: name `nmas-netbox-read`, bucket
`nmas-netbox-dmarchak` only, type **Read Only**, no file-name prefix, no
expiry. **Record the capability list B2 shows for it.** B10's check needs
the bucket's lifecycle rules and lock configuration, and whether a UI
read-only key can read those is a fact to take from that list, not an
assumption.

### 6b. The laptop

```bash
sudo apt-get install -y rclone
rclone config        # n) new remote, name b2-read, type b2; paste keyID and key AT THE PROMPT
                     #    (never on the command line: it would be in history and in ps)
stat -c '%a %n' ~/.config/rclone/rclone.conf     # must be 600
```

### 6c. Retrieve, then verify by the listing

```bash
rclone lsjson --files-only b2-read:nmas-netbox-dmarchak/daily    # names, sizes, times
mkdir -p ~/netbox-restore
rclone copy -v b2-read:nmas-netbox-dmarchak/daily ~/netbox-restore --include '<name>.tar.gpg'
ls -l ~/netbox-restore/<name>.tar.gpg    # the size MUST equal the listing's: rclone's exit 0 proves nothing
```

**After an attack**, if the files are hidden (B9), list and fetch the
versions:
`rclone lsjson --files-only --b2-versions b2-read:nmas-netbox-dmarchak/daily`,
then `rclone copy` with `--b2-versions` and `--include` naming the
`<name>-v<timestamp>.tar.gpg` version.

### 6d. Decrypt and check it is a whole backup

```bash
cd ~/netbox-restore
gpg -d <name>.tar.gpg | tar -tf -                           # must list netbox.pgdump, manifest.json, config/env/netbox.env
gpg -d <name>.tar.gpg | tar -xOf - manifest.json | head -40  # the row counts the restore will be compared against
```

### 6e. The read key cannot hide: a test that can fail

B9 is the lesson here: the command form must be shown to delete when
permitted, or its "not deleted" proves nothing. B9's own run is that
positive control, since this exact form HID a file with the write key. So,
with a fresh probe written by the write key from the NMAS:

```bash
# on the NMAS:
printf 'probe\n' > /tmp/readkey-probe.txt
rclone copyto --no-check-dest /tmp/readkey-probe.txt b2:nmas-netbox-dmarchak/readkey-probe.txt
# on the laptop, with the READ key:
rclone delete -vv b2-read:nmas-netbox-dmarchak --include readkey-probe.txt 2>&1 | tail -15
rclone lsjson --files-only b2-read:nmas-netbox-dmarchak | grep readkey-probe   # must still be listed
```

Pass: `-vv` shows a refusal, and the probe is still in the normal listing.
A `Deleted` line means the "read-only" key can hide, and it must not be kept.

## What this does not give

- **Point-in-time recovery.** Up to an hour of hand edits to NetBox between
  dumps is lost. NMAS's own writes are also in the modification record and
  the goldens.
- **An application-level restore.** The restore test proves the database, not
  that NetBox boots on it with the backed-up pepper. Booting a scratch
  NetBox on the restored data is the next step if that assurance is wanted.
- **Retrying a failed ship.** A failed push is recorded and the next hour's
  backup is shipped instead; the status goes stale if pushes keep failing.
