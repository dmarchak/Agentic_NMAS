# Update the app

The app updates itself from Help > About or Needs attention, to the newest release CI has
passed, without holding any privilege itself. What changes is the checkout on the host and
the process running from it; no network device is touched.

![The update: the app writes a request file and nothing else; a systemd path unit starts the root-owned updater, which re-checks the request and CI itself, moves the checkout as the service user, restarts the app, confirms the new commit by identity, and rolls back a version that does not come up; the page follows the updater's record and /health.](diagrams/update.svg)

## How it starts {#start}

About's **Update…** button and the Needs attention row for a running version behind
origin/main both open the Update page (`/v2/update`). So does **Update available** in the
top bar. It is drawn, in a neutral colour, only while origin/main is ahead of the running
commit AND CI passed a commit since it; hovering says how many commits it installs and since
when. A release
is news, not a problem, so it makes no Needs attention row. The pill turns into that row
when something IS wrong: CI failed or was cancelled for the release, the host has run
behind for more than 20 hours, the release could not be fetched, or an update asked from
this version did not happen. The two are never shown together. A release CI failed or
cancelled is never offered as an update: its row leads with the failure ("CI failed on the
newest commit, 74a7013 — run #373: <the step that failed>, in <the jobs>"), its action is the
developer's (fix forward with a newer commit; until CI passes one, the action names an older
commit CI passed, if there is one), and **Open run #N on GitHub** opens the run. Where it failed is read once per failed release
from the run's jobs on GitHub. What the page knows comes from the
app-pushed reader, which asks the repository's origin (`git ls-remote`) every 5 minutes and
when you press **Check again**, and asks GitHub's Actions API for CI's verdicts through
`nmas-deploy`'s own gate. No page load asks GitHub itself.

## The target {#target}

The target is the NEWEST commit since the running one that CI passed. While commits are
being pushed, the newest commit's CI is nearly always still running, and an older commit
that passed is a release you can install. The reader asks CI about each commit newest first,
and stops at the first one CI passed:

- a commit CI cancelled, failed or is still checking is never a target;
- nothing older than the running commit is ever asked or offered;
- with no commit passed since the running one, nothing is offered (if the newest is still
  being checked, you can wait for it: see below).

The commits beyond the target are said beside CI's verdict, counted by state ("3 newer: 1
running CI, 2 cancelled"), for information only. A final verdict is asked once; one read
asks GitHub about at most 6 commits, since GitHub answers 60 unauthenticated requests an
hour.

## The preview

The preview shows the commits between the running version and the target, the target's CI
verdict, what lies beyond it, the host steps of the commits up to the target (a step in a
commit beyond it is not this update's), and whether the checkout on the host is clean.
Each of these is a gate, and any failing refuses the update:

- the stored comparison is for the commit running now;
- origin/main is ahead of it, and fetched;
- CI passed the target;
- the checkout has no local changes;
- the updater is installed, root-owned, can run, and its path unit is watching;
- no update or terminal deploy is waiting or running;
- no operation is running on a device. The restart an update ends in would cut a deploy,
  restore, capture or rotation off half-applied, with no golden and no rollback (a
  deploy's or restore's devices that finished have their receipts, commit pending), so the gate names each device held and who is running what, and the update
  waits until they finish. An update already waiting for CI keeps waiting while one runs.
  A terminal `nmas-deploy` asks the same question before it restarts, and refuses (exit 10)
  naming each one.

An operation that a restart or a crash did cut off is a Needs attention row: what was
running, on which devices, who started it and its last step. Read each device and compare
it with its golden before changing it, then acknowledge the row with what you found.

Host steps come in two kinds. A `Host-Step:` must be done BEFORE the update: where the tool
can check it, it does so itself (done needs no tick; not done refuses, saying what it found);
otherwise you tick it as done. A `Host-Step-After:` never blocks: once the release runs, it
is a Needs attention row until it is checked done or you say **It is done**.

One artifact is one row. Steps checked by the same check (three re-installs of the Oxidized
helper, say) are one row naming every commit: the newest step's words lead, and the older
steps are superseded by it, since doing the newest does each. A step is checked by what it
did: the helper's pin is checked by the pin file (its owner, mode and the router.db it names),
never by the helper's hash, so a new helper release does not reopen it.

The confirm is bound to a hash of the running commit, the target, its CI state and the
before-steps; if any moved, nothing is requested and the new preview is shown.

## The steps, in order

The app writes a request and nothing else; a root-owned updater on the host does the rest,
and the Update page draws each step as the updater records it:

1. **The request** (`request`). Read: the preview, computed again. Sent: nothing. Recorded:
   a request file (its id, the target, the commit running now, you, the time, the
   before-steps you said are done), written in a staging folder and renamed into
   `data/update/requests/`, and a row in the app's `update_requests.jsonl`. A file appearing
   there is what starts the updater: the systemd path unit `nmas-update.path` watches the
   folder and starts `nmas-update.service`, which runs `/usr/local/sbin/nmas-update` as
   root. The app holds no privilege and runs nothing.
2. **The updater starts** (`started`). Read: the request folder (every entry is removed, so
   a request is acted on once; only a regular file the service user owns is read). Sent:
   nothing. Recorded: `/var/lib/nmas-update/outcome.json`, rewritten at every step from here
   on. The request must have exactly the updater's fields and be under 15 minutes old, or
   it is refused by field, never quoting its content. The updater then checks its own
   programs (by absolute path) and takes the lock a terminal `nmas-deploy` also takes, so
   one of the two moves the checkout at a time.
3. **The checkout is clean** (`checkout`). Read: `git status` of the checkout, run as the
   service user. Sent: nothing. Recorded: the step. Local changes refuse with nothing moved.
4. **Fetch** (`fetch`). Read: `git fetch origin`, as the service user. Sent: nothing.
   Recorded: the step. The checkout must still be at the commit the preview named, the
   target must still be ON origin/main (the tip, or older than it), and the target must be
   a fast-forward. Any of these failing refuses with nothing moved. A push made after you
   confirmed does not refuse your update: the commit you confirmed is still on
   origin/main, and the checkout moves to exactly it, never past it.
5. **CI, again** (`ci`). Read: GitHub's Actions API, through the updater's OWN root-owned
   copy of `nmas-deploy`'s gate, never the app's answer; and the `Host-Step:` lines of the
   commits between. Sent: nothing. Recorded: CI's sentence. Anything the gate does not pass,
   or a before-step the request does not say is done, refuses.
6. **Move** (`move`). Read: nothing. Sent: nothing. Recorded: the checkout fast-forwarded to
   the target (`git merge --ff-only`), as the service user. Git always runs as the service
   user (`runuser`): a repository can name programs in its config, and root never runs them.
7. **Restart** (`restart`). Read: systemd's MainPID for the app's unit. Sent: nothing.
   Recorded: the step. `systemctl restart` of the app's unit, the only thing done as root.
8. **Wait** (`wait`). Read: systemd's MainPID and `/health` on the host, every 2 seconds for
   up to 120 s. Sent: nothing. Recorded: the step. Success is decided by identity, never by
   time: the MainPID changed, `/health` answers from that pid, and it reports the target
   commit. A version that does not come up within 120 s is rolled back: the checkout is reset
   to the commit it ran, restarted, and confirmed the same way.
9. **Running** (`running`). Read: `/health`. Sent: nothing. Recorded: the outcome (updated,
   refused, rolled back, rollback failed, or failed) in `outcome.json` and appended to
   `history.jsonl`. This is the page's end state: the target is running.

While the updater works, the page asks `/health` and the app's status route (which reads the
updater's record) every 2 seconds and draws the step the record names; when the target is
running it reloads. A rollback, and a rollback that failed, are said in words.

## Update when CI passes

If CI is still checking the newest release and it is the only gate failing, you can choose
to update when it passes. Read: the preview. Sent: nothing. Recorded: a wait record
(`data/update/deferred.json`, you, the target, the hash) and a row in
`update_requests.jsonl`. After each of the app-pushed reader's reads (every 5 minutes, or on
**Check again**), the app looks at the wait. CI passing the commit you chose, with every
other gate passing, writes the request for exactly that commit as you, as above. A newer
push neither replaces nor ends the wait. Each of these ends it in words, with nothing
requested:

- a failed or cancelled CI run for your commit;
- the commit leaving origin/main;
- another gate failing;
- 25 minutes passing.

It never installs a newer release in place of the one you chose. **Stop waiting** ends it,
naming you.

## Check again {#check-again}

**Check again** asks origin and CI now. It is busy on itself until the answer arrives, which
is the panel redrawing with the new time. After an update's result or refusal, the panel
holds it against redraws nobody asked for, but your Check again releases that hold, so its
answer lands. A check that does not answer within its bound (2.5x the slowest recorded
check) gives up and says so, and the button works again without a reload. Pressing it while
that check is still owed an answer says how long ago it was asked.

## What the update does not do

- It never installs a commit CI has not passed, whatever the request says.
- It never runs anything from the repository as root.
- It changes no network device, intent, golden or setting.
- It does not do a host step for you: before-steps must be done first, after-steps stay on
  Needs attention until done.
