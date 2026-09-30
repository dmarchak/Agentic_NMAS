# The Update button (built 2026-09-30)

Needs attention says when the host runs a commit behind what is pushed. Its
action is **Update…**, which opens the Update page (`/v2/update`). Help > About
links to the same page when the host is behind: one page, two entry points.
Updating needs no terminal. CI decides WHAT can run, and a person decides WHEN.

## How it works

1. **The preview** is what the `app-pushed` reader stored, never a fetch made
   while the page loads. It shows:
   - the running commit and the target (origin/main);
   - the commits between them;
   - CI's verdict for the target, by `nmas-deploy`'s own gate;
   - each `Host-Step:` trailer, a box per step, saying "Done";
   - whether the checkout is clean;
   - whether the updater is installed as it must be;
   - since when origin/main has been ahead of the running commit.

   "Check again" asks origin and CI now instead of at the reader's next run
   (every 300 s).
2. **The confirm** is bound to a hash of what the preview showed. The apply
   recomputes it and refuses a preview that moved. It is gated `confirm`, so a
   verified person is required.
3. **The app writes a REQUEST and holds no privilege.** The request is one file
   in `data/update/requests/`, holding:
   - the target;
   - the commit it runs now;
   - the person;
   - the time;
   - the host steps the person said are done.

   The file is written outside that directory and renamed in. There is no sudo
   rule and no polkit grant. Each request is recorded in
   `data/update_requests.jsonl`.
4. **The root-owned updater** (`/usr/local/sbin/nmas-update`) is started by
   `nmas-update.path`. It treats the request as a request:
   - it reads the file without following a link, only if it is a regular file
     the service user owns;
   - it refuses a malformed or stale request (older than 15 min) by name,
     never quoting its content;
   - it RE-ASKS CI through its own root-owned copy of `nmas-deploy`'s gate;
   - it requires the target to still be origin/main after a fetch, and the
     checkout to be clean and at the commit the preview named;
   - it requires every host step to have been said done.

   So the most anything that can write the request can achieve is running a
   commit CI already passed.
5. **Git runs as the service user** (`runuser`, with that user's home). Only
   the restart runs as root. Nothing from the checkout is ever executed as
   root.
6. **Success is decided by identity**, as `nmas-deploy` decides it: systemd's
   MainPID changed, `/health` answers from that pid, and it reports the target
   commit. **A version that does not come up within 120 s is rolled back**: the
   checkout is reset to the commit it ran, the app restarted, and that is
   confirmed the same way.

   The 120 s comes from 120 restarts in the host's deploy audit: median 2.1 s,
   p90 10.2 s, and the slowest normal ones 17.5, 19.1 and 38.9 s. One took
   574.7 s and is not explained.
7. **The page waits on facts**: `/health`'s commit and the updater's record,
   never a timer. It says "the app is restarting" while nothing answers. A
   finished update reloads the page, and the page then draws **The last
   update**: updated, refused, rolled back, or ROLLBACK FAILED, with why. About
   shows it too.

   If the last update did not happen, the Needs attention row names it as its
   cause, and a failed rollback is a danger row.

The updater's record is `/var/lib/nmas-update/outcome.json` and
`history.jsonl`. Both are written by root, mode 0644, and read by the app.
Nothing root writes lands in the service user's directories.

## The one-time install (the operator's step: first installation)

On the NMAS host, in the checkout the service runs, as the service user (who
has sudo):

```bash
cd <checkout>                                     # the checkout flask-app.service runs
python3 -c 'import yaml' && echo yaml ok          # the gate's copy needs PyYAML in the system python
scripts/nmas-render-units --out /tmp/nmas-units deploy/systemd/nmas-update.path deploy/systemd/nmas-update.service
cat /tmp/nmas-units/nmas-update.path /tmp/nmas-units/nmas-update.service   # read what you install
sudo install -o root -g root -m 0755 deploy/update/nmas-update /usr/local/sbin/nmas-update
sudo install -d -o root -g root -m 0755 /usr/local/lib/nmas-update
sudo install -o root -g root -m 0644 scripts/nmas-deploy /usr/local/lib/nmas-update/nmas-deploy
sudo install -o root -g root -m 0644 /tmp/nmas-units/nmas-update.path /tmp/nmas-units/nmas-update.service /etc/systemd/system/
sudo install -d -o root -g root -m 0755 /var/lib/nmas-update
install -d -m 0700 data/update/requests data/update/staging        # as the service user, NOT sudo
sudo systemctl daemon-reload
sudo systemctl enable --now nmas-update.path
```

### The check

```bash
stat -c '%U:%G %a %n' /usr/local/sbin/nmas-update /usr/local/lib/nmas-update \
  /usr/local/lib/nmas-update/nmas-deploy /etc/systemd/system/nmas-update.path \
  /etc/systemd/system/nmas-update.service /var/lib/nmas-update
systemctl is-active nmas-update.path
scripts/nmas-update-check                          # as the service user, never sudo
```

Expected:
- every file and directory reads `root:root` with `755` or `644`;
- the path unit reads `active`;
- `nmas-update-check` exits 0, printing `updater: ok`.

`nmas-update-check` prints job health's own row (the same function). Job
health keeps asking. Its `updater` row is:
- **danger** (`writable`) if any of those files, or its directory, is not
  root-owned or can be written by the service user;
- **danger** if the path unit is not watching;
- **not installed** while it is absent;
- a warning (`differs`) when this release's copy has moved on from the
  installed one.

## Re-install

The installed updater and gate are COPIES, and they are what runs. When a
release changes `deploy/update/nmas-update`, `scripts/nmas-deploy` or either
unit:
- the Update preview says so;
- after the update, job health's row reads `differs`.

Re-install from the checkout, now at the new commit:

```bash
cd <checkout>
sudo install -o root -g root -m 0755 deploy/update/nmas-update /usr/local/sbin/nmas-update
sudo install -o root -g root -m 0644 scripts/nmas-deploy /usr/local/lib/nmas-update/nmas-deploy
scripts/nmas-render-units --out /tmp/nmas-units deploy/systemd/nmas-update.path deploy/systemd/nmas-update.service
sudo install -o root -g root -m 0644 /tmp/nmas-units/nmas-update.path /tmp/nmas-units/nmas-update.service /etc/systemd/system/
sudo systemctl daemon-reload
scripts/nmas-update-check
```

## A release that needs a host step

A commit whose code needs a person on the host before it can run (a new unit,
a package, a sudoers change) carries a `Host-Step: <what to do>` trailer, one
per step. The preview lists each with a box. The updater refuses the release
until the person has said each is done. The tool cannot verify a host step:
the box is the person's statement, and it is recorded in the request.

## What it does not do

- It runs nothing from the repository as root.
- It touches no device, no list's repository and no NetBox.
- It does not update itself (see Re-install).
- It rolls back only a version that does not come up within 120 s. A defect
  found later is fixed by the next release.
- `nmas-deploy` stays the host-side path. It and the updater do not lock each
  other, so running both at once is the operator's to avoid.
