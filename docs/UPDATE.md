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
5. **Git runs as the service user** (`/usr/sbin/runuser`, with that user's
   home). Only the restart runs as root. Nothing from the checkout is ever
   executed as root.

   **Every program the updater runs is named by its absolute path**, from one
   table (`BINARIES`: `/usr/sbin/runuser`, `/usr/bin/git`,
   `/usr/bin/systemctl`). A minimal PATH is right for a root process; resolving
   a program by name is what broke the second real run (C246).

   **The updater tests itself before every update.** Its self-test checks that
   each of those programs exists, is a regular file owned by root that only
   root can write, and is executable. If the self-test fails, the update is
   refused at "Updater started" and nothing moves.
6. **Success is decided by identity**, as `nmas-deploy` decides it: systemd's
   MainPID changed, `/health` answers from that pid, and it reports the target
   commit. **A version that does not come up within 120 s is rolled back**: the
   checkout is reset to the commit it ran, the app restarted, and that is
   confirmed the same way.

   The 120 s comes from 120 restarts in the host's deploy audit: median 2.1 s,
   p90 10.2 s, and the slowest normal ones 17.5, 19.1 and 38.9 s. One took
   574.7 s and is not explained.
7. **Every stage is visible, and the page waits on facts** (`/health`'s commit
   and the updater's record, never a timer). On click the button disables and
   reads "Sending the request…"; a refusal is shown on the page with its reason;
   once accepted, a STEPPER follows the updater's own steps (request written,
   updater started, checkout checked, fetched, CI re-checked, checkout moved,
   restarting, waiting for the new version with its seconds, running the
   target), each named by the key the updater's record carries.

   After a failure the stepper shows three states, never a bare list:
   - the completed steps are **done**;
   - the failed step reads "failed:" and its reason;
   - every later step is **not reached**, struck through and marked apart. A finished update reloads the page, which then draws **The
   last update**: updated, refused, rolled back, or ROLLBACK FAILED, with why.
   About shows it too.
   **The first real run (2026-09-30) did nothing and said nothing** (C243): the
   component read its attributes from the button instead of its root, so the
   button was disabled while looking clickable. Real-browser tests now click
   the shipped button (`tests/browser.py`, where Firefox runs).

   **The second real run (the same day) failed safely at the checkout step**
   (C246): `FileNotFoundError: runuser`. Nothing was moved, the request was
   consumed and the lock was released.

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
- `nmas-update-check` exits 0, printing `updater: ok` and
  `self-test: ok, every program it runs is present and root's`.

The self-test is the INSTALLED updater's own. It runs only after the check has
found the file root-owned and writable by nobody else, and it checks the same
absolute paths the updater runs. Ownership and modes alone could not have
caught C246.

`nmas-update-check` prints job health's own row (the same function). Job
health keeps asking. Its `updater` row is:
- **danger** (`writable`) if any of those files, or its directory, is not
  root-owned or can be written by the service user;
- **danger** (`cannot_run`) if its self-test fails: a program it runs is
  missing, not root's, or writable by someone else, or the installed copy
  predates the self-test;
- **danger** if the path unit is not watching;
- **not installed** while it is absent;
- a warning (`differs`) when this release's copy has moved on from the
  installed one.

## Re-install

**Required after the release that runs every program by absolute path
(C246):** it changes both copies. `deploy/update/nmas-update` gains the absolute
paths and the self-test, and `scripts/nmas-deploy` gains `unit_state`'s program
argument. The button cannot deliver this release, because the installed updater
is the one that fails. Deploy it from the terminal, then run the commands below
once.

`nmas-update-check` must then print `self-test: ok`. The copy installed before
this release has no self-test, so the check reads `cannot_run` until it is
re-installed.

(The same was required after the release that repaired the button, C243, for
the shared lock.)

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
until the person has said each is done. The tool cannot verify most host steps:
the box is the person's statement, and it is recorded in the request.

**A terminal deploy says the same, LAST on screen** (the operator, 2026-09-30:
08dbee5 needed the updater re-installed, `nmas-deploy` finished without a word,
and the updater stayed broken until job health caught it).
- After every deploy that leaves the checkout at the target, `nmas-deploy`
  prints each `Host-Step:` trailer of the commits it just deployed.
- **A step naming the updater is checked:** `nmas-deploy` runs
  `scripts/nmas-update-check`, and prints "Done", or "STILL NEEDED" with the
  exact commands.
- **Any other step** says it is not checkable from here, so confirm it by hand.
- **The updater's check runs on every deploy** where an updater is installed, so
  a step from an EARLIER release that is still undone is caught on the next
  deploy ("HOST STEP OUTSTANDING from an earlier release").
- A refusal before anything moved lists no steps.

**The exact commands have one owner:** `modules/update_op.py`'s
`REINSTALL_COMMANDS` and `INSTALL_COMMANDS`, each line held equal to this
document's by a test.
- Job health's `updater` row shows them on Needs attention with a copy button,
  this document as the detail.
- `nmas-update-check` prints them last.
- The row says when the condition began: the later of this release starting and
  the installed copy being written.

## What it does not do

- It runs nothing from the repository as root.
- It touches no device, no list's repository and no NetBox.
- It does not update itself (see Re-install).
- It rolls back only a version that does not come up within 120 s. A defect
  found later is fixed by the next release.
- `nmas-deploy` stays the host-side path. **It and the updater take ONE lock**
  (`data/update/lock`, C242): whichever holds it moves the checkout, and the
  other refuses by name (`nmas-deploy` exits 9). The Update preview shows a
  held lock as a failed check.

  The lock is a `flock` on an open file, never the file's presence. The file
  stays after every run (0 bytes) and blocks nobody. Each holder releases the
  lock on every path, and the kernel releases it if the holder dies. Tests
  cover a failure at every step, refused and failed, and a killed holder.

## Checking for an update

Help > About always offers **Check again**, which asks origin and CI now (the
reader otherwise asks every 300 s), so right after a push there is always a way
to ask. What it shows is stated as of when it was asked ("was the tip when last
asked"), never as a fact about now.

The row is the state, its timestamp and the button, nothing else (the
operator, 2026-09-30):
- while the check runs, the button reads **Checking…** and is disabled;
- it stays that way until the answer arrives, which is announced to the page
  even when nothing changed;
- the answer updates the row in place, and its timestamp reads "just now".
  That is the confirmation.

Words appear only when the person must act:
- a refusal ("Not asked: …");
- a failed check, shown beside the answer from before it;
- no answer within 2.5 times the slowest recorded run of the check (1.1 s
  measured on the host, so 3 s).

The Update page's Check again works the same way.

**The record stays, off the screen.** What caused each answer and how long it
took is on the timestamp's hover, for example "checked on your request, 1.1 s"
or "the scheduled check, 1.1 s". The reader's store keeps the last 20 runs with
their trigger and duration (`data/readers/app-pushed.json`, `runs`). A run on
request is logged in `logs/device_manager.log`:

```
reader app-pushed: run <id> on request by <person> took <N> ms: ok
```

**Found on the first check after the repair (C244, 2026-09-30):**
- the button reverted after 5 s because the request had been accepted, not
  because the check had finished;
- the reader announced only a changed answer, so a check that found nothing
  new reached no page;
- nothing recorded whether a click had run the check.

## A console message that is not a defect

Cloudflare's Web Analytics injects a beacon script into every page served
through the tunnel, and the pages' Content-Security-Policy blocks it, which the
browser console reports as a CSP violation. It is the policy working. The
policy is not widened for it; Web Analytics is turned off for the hostname in
Cloudflare instead (the operator, 2026-09-30).
