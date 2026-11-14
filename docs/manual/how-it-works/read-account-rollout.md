# Roll out the read-only account

**Add the read-only account…** on Credentials › Profiles writes the account into each chosen
device's committed intent (see [The read-only account](credentials#add-read-account)); nothing
reaches a device until that intent is deployed. The rollout deploys it through the batch
deploy, the same plan and apply every deploy runs ([Deploy a change](deploy)): one preview of
every chosen device's program and one hash, then the devices one at a time, a canary first, the
first failure stopping the rest. Board R, provisional, operator review pending.

![The read-only account's rollout (board R). Add the read-only account committed it to each device's intent; the rollout deploys that intent through the batch deploy. The preview sends nothing: each chosen device's program comes from the deploy's own plan, masked, in one order (the canary alone, then waves, then each device carrying Mercury's management path last and alone) under one hash, which you confirm. The run holds each device, sends its program, verifies it and saves it to startup, rolling it back if verify fails; it pauses after the canary for Go on, and before a management-path device for a confirm naming it. The first failure stops the rest. Each device's receipt and golden are recorded.](diagrams/read-account-rollout.svg)

## Where it is {#where}

On **Credentials › Profiles**, the card **Read-only account on the devices**: **Roll it out…**
beside **Add the read-only account…**, and the same form under an Add's result. Choose the
**Network**; the devices it offers, each ticked, are those whose committed intent names the
account and whose golden does not hold it yet (the coverage as last read). Untick any to leave
out. Choose the **Canary** (one of them; by default the first the plan sends to) and **Then
waves of** (four by default, at most fifty). **Preview the rollout** starts the preview;
**Cancel** closes the card with nothing changed.

## The preview {#preview}

1. `preview`. Read: each chosen device's committed intent, its golden and its template, through
   the deploy's own plan, and the Topology read. Sent: nothing. Recorded: nothing. It runs as a
   job, and the card redraws when it ends. Each device's program is its exact lines, masked;
   a program holding lines besides the account's (intent committed earlier and not yet
   deployed) says how many, and they are sent with it. A device whose program is empty sends
   nothing; a device the deploy refuses is named with its reasons. **The order:** the canary
   alone, then the rest in waves of the chosen size, then each device that carries Mercury's
   management path to another device (it lies on a shortest path from Mercury's host to it, in
   the Topology read), last and alone, naming the devices reached through it. **When the
   Topology read cannot be used, the rollout is not offered**: a guard that cannot read its
   input neither passes nor fails, so the preview says the management path could not be
   measured and why, and draws no **Deploy the canary**; a confirm sent anyway is refused,
   naming what it compared (the Topology read must be usable, and is not; or you name the
   devices that carry it, and you named none), and nothing is sent. Under **Devices that
   carry Mercury's management path, named by you** in the form, tick each device that
   carries it; each then goes last, alone, on its own confirm, as a measured one does (a
   device you name is held back even when the read works). One hash binds every device's
   program, the order, the devices you named and the repository's commit.

## The run {#run}

2. `confirm`. **Deploy the canary**, as a verified person, confirms the hash. The plan is made
   again; a program, the order or the repository that moved since refuses the run, naming both
   hashes, and nothing is sent.
3. `canary`. The canary alone, through the deploy's apply: held, its program recomputed and
   refused if it moved, sent merge-only, verified, saved to startup only once it verified,
   rolled back if verify fails. The run then pauses: **Go on: the next waves** continues.
4. `waves`. Each wave in turn, each device's program checked against the confirmed one before
   it is sent, then held, sent, verified and saved as the canary was. The card draws each
   device's state in place: waiting, deployed, verified and saved, verify failed and rolled
   back, or not attempted.
5. `management`. Before a device that carries Mercury's management path, the run waits again:
   the card says how many devices Mercury reaches through it, and **Deploy <device> (the
   management path)** is its own confirm, naming that device. A confirm naming another device
   is refused, naming both. Not pressed, nothing more is sent: the run stays paused, the
   device's intent stays committed, and the coverage says "intent says it, not deployed yet".
6. `stop`. The first device that does not deploy and verify stops the run: it is rolled back
   on its own, and every device after it is not attempted. **Preview the rollout again…**
   starts a new preview.
7. `record`. Each device's receipt, whatever happened, and its golden committed after its
   save, both on its History. The coverage reads again when the goldens are committed.

Every press needs a verified person: the confirm and each Go on are deploys. A server restart
loses a paused run's place (it is held in this server's memory): what it did is in each
device's History, and a new preview starts from what is committed.
