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
   compiles each app's start-time config from what its manifest declares (each expected
   switch's tables, placed from its platform profile), checks conformance for every expected
   switch, reads what the unit's own command line has that is not Mercury's to manage (its
   REST bind, its other flags, the apps it loads: [what is kept](#kept)), and renders the
   drop-in the apply script will write, carrying them. A refusal names what it compared, and
   nothing is staged on the controller. The preview removes what it staged here before it
   answers.
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
   command's wait and the post-check's two bounds (room for a rollback). Inside it the controller's
   restart is planned, not unplanned, and its switches' drops are its expected effect; it ends
   when the post-check passes, or at once when nothing restarted, and otherwise runs to its end.
5. `stage`: the files go over SFTP as the deploy account, only into
   `/opt/ryu-apps/<app>/<version>/`, each checked against its blob first; an app's start-time
   config, when it has one, is staged beside its version with its hash in the request; the
   request is written last. Nothing is deleted on the controller.
6. `command`: `sudo -n /usr/local/sbin/mercury-ryu-apply`, with no argument: the only thing the
   deploy account may run as root. The script checks the request and every folder's hash
   again, reads the unit's own command line itself and refuses a request that keeps anything
   else of it, writes the drop-in (keeping the one before as `mercury.conf.prev`), restarts
   the unit and judges it by identity: a new MainPID, active, User `ryu`, within 75 s on its
   own steady clock. Its outcome is read back.
7. `post-check`: first Ryu must answer, within 75 s of the outcome being read back; then
   every expected switch (by its DPID in the controller's switch list), every link NetBox
   cables between OpenFlow ports, and every enabled app's /health, within 55 s of Ryu's first
   answer. Both run on Mercury's own clock ([the bounds](#bounds)). Each switch's time is
   counted from the restart.
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
  where it listens for OpenFlow, and where Ryu's REST is bound, in words: the address the unit
  names, kept as it is, or that it answers on every address when the unit names none or
  already binds every address.
- **The set, in load order**: each app with its version, its pin (commit and content hash) and
  its files; the app that changes marked, and its files listed. Ryu's own `ofctl_rest` and
  `rest_topology` always load last.
- **From the unit's own command line, carried as it is**, when the unit has anything Mercury
  does not manage: each app it loads, "kept: … not managed by Mercury" or "replaced: …" by the
  set's app of the same name, and its other flags ([what is kept](#kept)).
- **Each app's start-time config**, when it has one: where it is staged, whether it is new,
  changed or the same as the controller's record, its hash (in the request, so the confirm
  binds it), each switch's tables and the platform profile they were placed from (table 0 where
  the profile records no tables), and the config itself, masked. The app reads it once, at
  load, so it serves after the restart without anything pushed to it.
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
cannot connect, a config that holds a secret, a config that cannot be compiled (a switch no
platform profile covers, a table no role fits, or a value the app's schema refuses, each named),
Mercury's record of the set that cannot be read, a unit's own command line that cannot be
carried as it is, or a drop-in that would drop, widen or change Ryu's REST bind or stop loading
something the unit loads now ([what is kept](#kept)).

## A controller as it is: what is kept {#kept}

Mercury takes a controller as it finds it. Its unit may already bind Ryu's REST to one address
and load apps of its own, put there before Mercury managed it. Nothing of that is dropped
without a word, and nothing is edited by hand first.

- **What is read.** The command line the unit runs without Mercury's drop-in: the `ExecStart`
  its unit file and its other drop-ins leave (`systemctl cat`, one of the host's three reads).
- **What is Mercury's.** The set's apps, Ryu's own `ofctl_rest` and `rest_topology`,
  `--observe-links`, and the OpenFlow listen address and port, which are NetBox's `openflow`
  Service's. When the unit listens elsewhere today, the plan says both.
- **What is kept.** Everything else, in the unit's order: Ryu's REST bind (`--wsapi-host`,
  `--wsapi-port`), every other flag, and every app the unit loads. A kept app is drawn as
  "kept: <its file>, loaded from <its folder>, not managed by Mercury": it is not read, tested
  or versioned by Mercury, its OpenFlow versions are not in the conformance check, and it loads
  before the set's apps. The apply script reads each kept file as root when it applies and
  records its hash in the receipt, so a change to one shows between two receipts.
- **Adopting a kept app.** Deploy an app of the same name through Mercury (add it as a Draft,
  run its tests, publish it, preview its deploy). The plan then draws the file as "replaced":
  it is no longer loaded, Mercury's version takes its place, and the file stays on the
  controller. Two apps of one name cannot load in one controller, so there is no state with
  both.
- **REST's bind is never widened.** The drop-in carries the address and port the unit names
  and nothing else. A unit that names none gets none. A bind to every address (`0.0.0.0` or
  `::`) is written only when the unit already has it, and the plan says so in words. Mercury's
  own reads of Ryu's REST go to the address the network's controller connection names, never
  an assumed one, so that connection must name an address REST is bound to.
- **Two reads, compared.** What is kept comes from the unit's own files. The plan then
  compares the drop-in it would write with the command line systemd holds now (`systemctl
  show`), and refuses, naming both values, if the deploy would drop, widen or change the REST
  bind, drop a flag, or stop loading an app that nothing in the set replaces. The apply script
  makes the first read again itself, as root, and refuses a request whose kept arguments
  differ from the unit's.
- **What is refused, by name.** An argument that is not one plain word (quoted, escaped, or
  expanded by systemd), named by its position; a REST address that is a name, not an IPv4 or
  IPv6 address; more than one `ExecStart`; a drop-in read after `mercury.conf` that sets
  `ExecStart`, since Mercury's would not be the one that runs.

Not built: removing a kept app that nothing replaces (a deploy never drops one), and taking a
kept app's file into the code repository as it is; an app enters the repository as a Draft, by
a person.

## Installing the apply script, once {#install}

The deploy's one privileged command is a script installed on the controller host, root-owned.
Installing it is the one step a person makes on the controller, once per controller, as their
own account with sudo, from a copy of this release:

`bash <release>/scripts/host-steps/p6-controller-apply-install.sh <unit>`

`<unit>` is the systemd unit Ryu runs as, the controller's `openflow.unit` (the controller's
card on [SDN › Apps](sdn#apps) names it). It takes the controller as it is and edits no file by
hand before or after:

- **Before it changes anything** it checks, and stops at the first that fails, saying what it
  wanted and what it got: the accounts `mercury` and `ryu` exist; the sudoers file is absent or
  holds exactly the one line; the unit's command line can be carried whole (the same read the
  deploy makes); the `ryu` account can read every app the unit loads; Ryu lists its switches at
  the address its REST is bound to; and the unit already runs as `ryu`, or the run was told it
  may restart it.
- **Then** it installs the script, the sudoers line when its file is absent, and a first
  drop-in that sets `User=ryu` and nothing else. A unit that already runs as `ryu` is not
  restarted. One that does not is restarted only when `restart` follows the unit's name. Its
  planned-restart window is declared first, and no screen declares one for a host step yet (a
  gap: only a deploy and a device's Reload declare their own). Ryu must then answer within
  75 s and every switch it listed before must be back within 55 s of that answer, or the
  drop-in is taken out again.
- **Last**, with `User=ryu` read back, it hands `/opt/ryu-apps` to the deploy account. Apps the
  unit loads from that folder stay where they are and are kept by every deploy.
- **Run again** it changes nothing that is already in place: a `mercury.conf` that is there (a
  deploy's) is left as it is.

Everything after it is this operation: preview, confirm, apply, post-check, rollback, record.

## Where each fact comes from {#sources}

- **The controller host** is the device NetBox's `openflow` Service is on, read from the
  network's committed NSOT export, never from NetBox live and never from an uncommitted edit.
  Ryu listens on that Service's own address, or else the device's primary IPv4 or IPv6
  address, at the Service's port. The systemd unit Ryu runs as is the device's config context
  key `openflow.unit`. When the network has more than one controller connection,
  `openflow.connection` names the one this host answers on. Mercury reaches the host with the
  login its inventory holds for it.
- **The host's three reads** (`systemctl show -p User -p ExecStart <unit>`,
  `ls -la /opt/ryu-apps` and `systemctl cat <unit>`) are asked at each preview, and again at
  the confirm while the controller is held. They go through the same engine as Show commands,
  so each run is recorded and History › Reads lists it. The controller's card draws the newest
  run that holds both of its unit's reads.
- **The expected switches** are the devices whose OpenFlow values name this controller, each
  identified by its `openflow_datapath_id`. **The expected links** are the connected cables
  between their OpenFlow ports. Each port is numbered by its `openflow_port`, or by its
  platform's own numbering where that numbering identifies it.
- **What is connected now** is the controller's own switch and link lists, read through its
  controller connection.
- **The app versions** come from the app registry, which is not built yet. Until it is, no
  version can be listed, and every preview says so.
- **An app's /health** is read through the same controller connection, at the REST prefix the
  app's manifest declares: `GET <prefix>/health`, one request each, bounded at 5 s (a
  placeholder until a deploy's receipt measures the read), or the connection's own timeout
  when that is shorter. The app answers whether it is healthy and, when it is not, why. No
  answer, or no such path (the app is not loaded), is said as no answer; an answer that is not
  a /health answer is said as unreadable, naming what failed. Neither passes the post-check.
  After a rollback, the apps read are the ones the rollback put back.

A host, switch or cable missing one of these facts is named where the fact is needed. For
example: a host with no `openflow.unit`, a host the inventory does not hold, or a cable end
with no OpenFlow port number. The plan is then refused and nothing is sent; a host with no
unit, or one the inventory does not hold, is not read either.

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

## The bounds {#bounds}

Each is about 2.5 times a measured time, and each is counted on a clock that cannot jump: a
controller's wall clock can be years wrong after a boot until NTP corrects it, so no bound
uses a time read on the controller.

| Bound | How long | Measured | Counted from, on whose clock |
|---|---|---|---|
| The unit is active again | 75 s | Ryu answered within 30 s of its process starting | the restart call returning, on the apply script's steady clock |
| Ryu answers | 75 s | the same 30 s | the apply's outcome being read back, on Mercury's clock |
| Every switch, link and /health is back | 55 s | every switch and link was back 21 s after Ryu answered (52.5 s, taken up to a whole 5 s read) | Ryu's first answer, as Mercury saw it |

The measurement is a controller reboot (2026-11-11). A bound that fires says which it was,
what it read and how many times, what it waited for, and this measurement; the deploy then
rolls back. Each deploy's receipt keeps every switch's own time after the restart.

See also: [SDN › Apps](sdn#apps) · [Change an SDN switch's flows](sdn-flows).
