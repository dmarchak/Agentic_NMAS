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

- this installation takes the in-app update. A laptop kit (`installation_kind` laptop_kit)
  does not: it is pinned to one commit and moves only by `kit repin <sha>`
  (docs/LAB9_LAPTOP_RUN.md). On a kit the top bar's Update is drawn held, saying so, the
  preview leads with this gate, and a confirm or a wait for CI is refused naming the
  installation kind, before anything is written;
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
- no SDN loop is running. The restart would stop it, and it does not resume by itself; a
  person stops it first.
- the update runs the safe-deploy script's gates: the refusal while an SDN loop runs, and the
  page smoke after the restart, rolling back on a failure. It passes only while the installed
  updater is the repository's and declares them. Until one that does is installed (a host
  step), the update is not offered, the top bar's Update names the commit it would install
  and is drawn held, saying why, and a deploy goes through the safe-deploy script.

An operation that a restart or a crash did cut off is a Needs attention row: what was
running, on which devices, who started it and its last step. Read each device and compare
it with its golden before changing it, then acknowledge the row with what you found.

Host steps come in two kinds. A `Host-Step:` must be done BEFORE the update: where the tool
can check it, it does so itself (done needs no tick; not done refuses, saying what it found);
otherwise you tick it as done. A `Host-Step-After:` never blocks: once the release runs, it
is a Needs attention row until it is checked done, you say **It is done**, or you decline it
with a reason (below). Done steps stay on the page: **Host steps said done** names who said
so and when, **Host steps the tool checked done** names each check and what it read, and
**Host steps declined** names who declined each, when and why.

One artifact is one row. Steps checked by the same check (three re-links of the topology
renderer, say) are one row naming every commit: the newest step's words lead, and the older
steps are superseded by it, since doing the newest does each. A step whose artifact is retired (the Oxidized helper and its pin, since 2026-10-08) reads
done: nothing runs it, and its removal is a host step of its own.

The confirm, **Update to <commit>** (**Update to <commit> when CI passes** when the wait
below is offered), needs a verified person. It is bound to a hash of the running commit, the
target, its CI state and the before-steps; if any moved, nothing is requested and the new
preview is shown.

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
   or a before-step the request does not say is done, refuses. Then the venv: the target's
   `requirements.lock` and `requirements-test.txt` name the virtualenv it needs. When that is
   not the one the app runs and it is not built and proved on the host, the update refuses
   with nothing moved, naming both and the host step that builds it.
6. **Move** (`move`). Read: nothing. Sent: nothing. Recorded: the checkout fast-forwarded to
   the target (`git merge --ff-only`), as the service user. Git always runs as the service
   user (`runuser`): a repository can name programs in its config, and root never runs them.
7. **Restart** (`restart`). Read: systemd's MainPID for the app's unit. Sent: nothing.
   Recorded: the step. When the target needs another venv, the link `/opt/mercury-venv` is
   moved to it first (the running one recorded as the previous), and a link that cannot move
   puts the checkout back with nothing restarted. Then `systemctl restart` of the app's unit.
   The link and the restart are the only things done as root.
8. **Wait** (`wait`). Read: systemd's MainPID and `/health` on the host, every 2 seconds for
   up to 120 s. Sent: nothing. Recorded: the step. Success is decided by identity, never by
   time: the MainPID changed, `/health` answers from that pid, and it reports the target
   commit. A version that does not come up within 120 s is rolled back: the checkout is reset
   to the commit it ran (and the venv link to the venv it ran, when the update moved it),
   restarted, and confirmed the same way. After a venv moved and the target came up, the venvs
   older than the previous one that no running process has loaded are removed. Once the app
   runs the target, every other long-running unit that runs the checkout's code (today the ZTP
   responder) is restarted with `systemctl try-restart` and confirmed by its new MainPID; one
   not running is left, and its next start loads the new code. A terminal `nmas-deploy` does
   the same (C1404: a responder that kept its old code refused a device the new code serves).
9. **Ready** (`ready`). Read: `/health` on the host, every 2 seconds for up to 100 s (about
   2.5x the 40 s the first pages after a restart waited on 2026-11-04). Sent: nothing.
   Recorded: the step, and the readiness the outcome carries (its state, the step, its
   error, the seconds waited). The new version runs; this asks whether it can serve: `/health`
   says `ready` only once each of its warm-up steps has finished without an error. Ready
   within the bound goes on. A warm-up step that failed, or a version still warming at 100 s,
   ends the update **FAILED, not ready**, naming the step and its error, or the step still
   warming. It is NOT rolled back: the version came up, so the decision is yours. Needs
   attention raises a critical row, "The deployed release <commit> is not ready: <step>
   failed: <error>" (or "still warming after 100 s"), whose action is the rollback to the
   release it replaced. Mercury has no one-click rollback yet: the row names the developer's
   `scripts/nmas-rollback <commit> --push`, after which this page offers the rollback as an
   update. The row clears once `/health` says ready, or once another release runs.
   A version whose `/health` has no `ready` (from before the warm-up) is said and not waited
   for. While it warms, the stepper shows this step with `/health`'s own reason, never
   Updated. A terminal `nmas-deploy` waits the same way, with the same bound, and ends with
   exit 11 when it is not ready.
10. **Running** (`running`). Read: `/health`. Sent: nothing. Recorded: the outcome (updated,
   updated with a unit not restarted, which is a warning naming the unit and the command,
   not ready (FAILED, above), refused, rolled back, rollback failed, or failed) in
   `outcome.json` and appended to `history.jsonl`. This is the page's end state: the target
   is running and ready.

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

## Declining a host step {#declining-a-host-step}

Some after-steps are never to be done here: a step for a part the installation has chosen
not to run (the local CI runner, when CI stays on GitHub-hosted runners). Each step under
**Still to do on the host** offers **Decline this step…** beside **It is done**. It opens a
reason box in place; type why the step is not to be done (at least three words) and press
**Decline the step**, which is busy on itself until the answer arrives.

- Read: the steps the running release owes, from its commits' trailers. Sent: nothing; no
  command runs on the host. Recorded: the decline, beside the done record in the same store
  (`data/host_steps_done.jsonl`, or the records database once it is moved there): you, how
  your identity was established, the time and the reason, masked as every typed reason is.
- The panel draws the answer in place: the step leaves **Still to do on the host** and is
  listed under **Host steps declined** as "Declined by <you> at <time>: <reason>. It is no
  longer owed; History keeps it." Its Needs attention row leaves too, and History lists it
  under **Host steps done or declined**, as it lists a step said done.
- One row asked for by several commits is declined for each of them.
- Declining never says a step is done. A step with a check can be declined too, and if its
  check later reads done, it moves to **Host steps the tool checked done**: done stays the
  check's.
- Refused, nothing recorded, the refusal drawn under the list: no reason, or one without the
  shape of one; a step already declined or said done (naming who did so, and when); a step
  the running release does not owe; a request that is not a verified person's.

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
- It never rolls back a version that came up and is not ready: that is FAILED, and the
  rollback is yours to choose from its Needs attention row.
- It changes no network device, intent, golden or setting.
- It does not do a host step for you: before-steps must be done first, after-steps stay on
  Needs attention until done or declined with a reason.
