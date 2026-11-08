# Deploy apps to an SDN controller

A network's controller apps (Ryu apps such as `of_versions`, `switch_quirks` and
`dns_blacklist`) come from the network's code repository. Only a Published version deploys,
byte for byte the version reviewed. Every deploy sends the whole set the controller will run
and restarts the controller, so every switch drops and reconnects; Mercury checks they all come
back and, if they don't, puts the set before back. You start it on [SDN › Apps](sdn#apps).

![A controller app deploy: the plan reads the controller host's unit, its app folder and its drop-in, stages each chosen version from git's blobs at its pin and checks its hash, checks conformance for every expected switch and renders the drop-in; a refusal sends nothing. You confirm, bound to the plan's hash; holding the controller, the plan is made again and a moved hash sends nothing; the planned-restart window is declared; the files and the request are staged over SFTP; the one command writes the drop-in and restarts the controller; the post-check waits for every expected switch, link and app's /health; a miss applies the request before (or puts the drop-in before back) and post-checks again; the receipt records it, and History shows it.](diagrams/controller-app-deploy.svg)

## The steps

1. `plan`: Mercury reads the controller host (its unit's User and command line, the app
   folder's owner and mode, its drop-in), stages each app's folder from git's blobs at its
   pinned commit into a folder of its own and checks its hash against the Published pin,
   checks conformance for every expected switch, and renders the drop-in the apply script will
   write. A refusal names what it compared, and nothing is staged on the controller. The
   preview removes what it staged here before it answers.
2. `confirm`: you confirm as yourself, a verified person; the button names the work ("Deploy
   switch_quirks 1.3.0 and restart ctl-1"), a first deploy's missing rollback ("… with no
   rollback") and what the post-check expects to recover ("… expecting dns_blacklist's /health
   to recover").
3. `hold`: the controller is held as one operation for the whole deploy, its rollback included:
   another deploy, a write or a Reload of it is refused by name while it runs, never queued. At
   the confirm the plan is made again, holding it: a different hash sends nothing, declares no
   window, and says what moved, both hashes.
4. `window`: a planned-restart window is recorded for the controller, its switches expected to
   drop, before anything is sent. Its length is twice the session's opening bound, the apply
   command's wait and the post-check's bound (room for a rollback). Inside it the controller's
   restart is planned, not unplanned, and its switches' drops are its expected effect; it ends
   when the post-check passes, or at once when nothing restarted, and otherwise runs to its end.
5. `stage`: the files go over SFTP as the deploy account, only into
   `/opt/ryu-apps/<app>/<version>/`, each checked against its blob first; an app's start-time
   config, when it has one, is staged beside its version with its hash in the request; the
   request is written last. Nothing is deleted on the controller.
6. `command`: `sudo -n /usr/local/sbin/mercury-ryu-apply`, with no argument: the only thing the
   deploy account may run as root. The script checks the request and every folder's hash
   again, writes the drop-in (keeping the one before as `mercury.conf.prev`), restarts the unit
   and judges it by identity: a new MainPID, active, User `ryu`. Its outcome is read back.
7. `post-check`: every expected switch (by its DPID in the controller's switch list), every
   link NetBox cables between OpenFlow ports, and every enabled app's /health, within a bound
   shown with where it comes from. Each switch's time is counted from the restart.
8. `rollback`: on a miss, or an apply that failed after the new drop-in was written, Mercury
   applies the request the controller ran before by its record, staged again from its pins, and
   checks again. On a first deploy it sends the second request kind instead, which puts the
   drop-in before back. The script never rolls back by itself. An outcome that could not be read
   is never rolled back by itself: a rollback is offered as a preview.
9. `record`: the receipt, kept with the other receipts and masked as History masks, for every
   outcome, a refused confirm included. History lists it under Controller app deploys.

## Choosing a version {#versions}

A version is chosen on its app's page (SDN › Apps, the app's row). "Preview deploying
<version>…" previews the set the controller runs by Mercury's record, with that one app at that
version (added when the set does not hold it). A Draft is never offered: it deploys only in the
container harness. The version the controller runs is not offered either; to deploy the same set
again, use the redeploy (below).

## The plan {#plan}

**Preview a deploy…** (on the controller's card) and "Preview deploying <version>…" (on an
app's page) open the plan in place. Everything you confirm is in one card:
- **The target**: the controller, its unit and User as read, the app folder's owner and mode,
  and where it listens.
- **The set, in load order**: each app with its version, its pin (commit and content hash) and
  its files; the app that changes marked, and its files listed. Ryu's own `ofctl_rest` and
  `rest_topology` always load last.
- **Conformance**: the OpenFlow versions the controller offers (the ones every loaded app
  shares) and each expected switch's.
- **The drop-in, before and after**, the lines that leave struck through and the new ones
  marked.
- **The restart, and what must come back**: the switches, links and apps' /health the
  post-check waits for, its bound, and what is already missing or failing now (expected to
  recover, or the deploy will miss and roll back).
- **Before, and if it misses**: the window, the hold, what is sent, what a miss rolls back to,
  and the plan's hash.

A plan that is refused draws each refusal in place of the confirm, naming what it compared and
both operands: the unit running as root over a folder the deploy account may write (C2), a
folder it cannot stage into, a User or command line that cannot be read, a requirement missing
from the set, a version that is not Published or whose staged hash is not its pin, a switch that
cannot connect, a config that holds a secret, or Mercury's record of the set that cannot be
read.

## A plan that changes nothing {#redeploy}

When the controller already runs the chosen set (every app at the chosen version, the drop-in
the same as its render), the card says so, **Nothing to deploy**: deploying it would change no
file and no line and would still restart the controller. **Redeploy the same set and restart
<controller>…** opens the full plan anyway, whose confirm reads "Redeploy the same set and
restart <controller>". It is how drift is repaired (a drop-in edited on the host), and it is
offered on a drifted controller's card as **Preview the redeploy…**.

## The confirm {#confirm}

The confirm is one decision with one control. Mercury makes the plan again holding the
controller; if its hash is not the one you confirmed, nothing is staged or sent and the card
says what moved (the request, the drop-in before or after, the unit, what the post-check
expects, or the rollback target), each hash then and now. **Cancel** leaves the plan and sends
nothing.

## While it runs, and the result {#running}

The confirm is busy on itself, **Deploying…**, and the card draws the steps as they go (the
one stepper): the plan made again, the window, staging, the command and its outcome, the
post-check with what is not back yet, a rollback, the record. On every other page the top
bar's In progress chip lists the controller as held. There is no Cancel once the command is
sent: the restart cannot be taken back mid-way, and closing the tab changes nothing; the
operation runs to its receipt either way.

What each result means:
- **Deployed** (green): everything came back, each switch with its time after the restart.
- **Rolled back**: it missed, and the set before is back (or, on a first deploy, the drop-in
  before).
- **Rollback failed**: it missed and so did the rollback; the controller and any switch not
  back stay rows on Needs attention after the window.
- **Not rolled back**: it missed and nothing could be rolled back (no request before and no
  drop-in before); the receipt names the break-glass, `mercury.conf.prev` on the controller.
- **Failed**: it stopped before the drop-in was written; the receipt says what was staged, and
  nothing restarted.
- **Unknown**: the command was sent and this run's outcome was not read.
- **Refused**: nothing was sent (the plan moved, or the controller was held).

Each result offers **Open the receipt** and **Back to Apps**; one that sent nothing, stopped
before the drop-in was written, or could roll nothing back offers **Preview again**. An
**Unknown** result offers **Preview a rollback…**, the plan of the set before the deploy, which
you confirm like any deploy: Mercury never rolls back by itself when it cannot tell whether the
command ran. A result that is a row on Needs attention (Unknown, Rollback failed, Not rolled
back) offers **Open its Needs attention row**.

## On Needs attention

A controller whose last deploy ended **Unknown** is a row ("<controller>'s deploy outcome is not
known"), and one whose last deploy ended **Rollback failed** or **Not rolled back** is a red row
("<controller> is not back as it was …"). Each names the deploy, who confirmed it and why it
ended so, and opens its receipt on SDN › Apps. It clears when the controller's next deploy
leaves it running a set Mercury recorded (deployed, or rolled back to the request before); a
refused confirm or a deploy that failed before the drop-in was written changes nothing, so the
row stays. Receipts that cannot be read are a row of their own: until they are repaired, a
deploy is refused.

## The bounds

Both are about 2.5 times a measured time. Until they are measured, each is marked a placeholder
wherever it appears, and the receipt keeps that.

See also: [SDN › Apps](sdn#apps) · [Change an SDN switch's flows](sdn-flows).
