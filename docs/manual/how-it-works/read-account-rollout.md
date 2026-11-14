# Roll out the read-only account

**Add the read-only account…** on Credentials › Profiles writes the account into each chosen
device's committed intent (see [The read-only account](credentials#add-read-account)); nothing
reaches a device until that intent is deployed. The rollout deploys it through the batch
deploy, the same plan and apply every deploy runs ([Deploy a change](deploy)), and the same
engine every batch deploy runs: one preview of every chosen device's program and one hash,
confirmed once; then the canary and every wave run by themselves, the first failure rolled back
and the run stopped, the team told. Board R, provisional, operator review pending.

![The read-only account's rollout (board R). Add the read-only account committed it to each device's intent; the rollout deploys that intent through the batch deploy's engine. The preview sends nothing: each chosen device's program comes from the deploy's own plan, masked, in one order (the canary alone, then waves, then each device carrying Mercury's management path last, after every device reached through it) with its options, under one hash, which you confirm once. Then the run goes by itself: each device held, sent, verified, probed signed in as the read-only account, and saved to startup; the settle waited between waves; a pause after the canary only when you chose one. The first failure, a failed probe included, is rolled back, stops the rest and tells the team. Each device's receipt and golden are recorded.](diagrams/read-account-rollout.svg)

## Where it is {#where}

On **Credentials › Profiles**, the card **Read-only account on the devices**: **Roll it out…**
beside **Add the read-only account…**, and the same form under an Add's result. Choose the
**Network**; the devices it offers, each ticked, are those whose committed intent names the
account and whose golden does not hold it yet (the coverage as last read). Untick any to leave
out. Choose the **Canary** (one of them; by default the first the plan sends to), **Then
waves of** (four by default, at most fifty), **Settle between waves (seconds)** (none by
default) and whether to **Pause after the canary for my Continue** (off by default).
**Preview the rollout** starts the preview; **Cancel** closes the card with nothing changed.
The preview and the run are background operations: leave the page and **In progress** keeps
them, and their result waits under **Finished, not opened yet** until you open it, which
reopens this card where you left it.

## The preview {#preview}

1. `preview`. Read: each chosen device's committed intent, its golden and its template, through
   the deploy's own plan, and the Topology read. Sent: nothing. Recorded: nothing. It runs as a
   job, and the card redraws when it ends. Each device's program is its exact lines, masked;
   a program holding lines besides the account's (intent committed earlier and not yet
   deployed) says how many, and they are sent with it. A device whose program is empty sends
   nothing; a device the deploy refuses is named with its reasons. **Each device's probe** is
   planned too, touching no device (the same plan as a coverage row's probe): the
   account it signs in as, how many of the AI's reads it asks and how many commands it must be
   refused, and any read not measured because Mercury holds no argument for it; a device whose
   probe cannot be planned (no read-only account resolves for it) is refused, naming why. **The order:** the canary
   alone, then the rest in waves of the chosen size, then each device that carries Mercury's
   management path to another device (it lies on a shortest path from Mercury's host to it, in
   the Topology read), last and alone, in dependency order: a device goes only after every
   device reached through it, a tie by name; carriers that reach each other refuse the plan,
   naming them. **A program of accounts and privilege lines alone** (the account's `username`
   line and `privilege exec` lines, and nothing else) cannot cut a management path, so its
   device joins the normal waves even when it carries the path, and the plan says so. **A
   canary you chose that cannot be the canary** (it carries the path, sends nothing, is refused
   or is not among the devices) refuses the preview, saying which and why: it is never
   replaced silently. **When the Topology read cannot be used, the rollout is not offered**
   while any program could cut a path: a guard that cannot read its input neither passes nor
   fails, so the preview says the management path could not be measured and why, and draws no
   **Deploy the canary**; a confirm sent anyway is refused, naming what it compared (the
   Topology read must be usable, and is not; or you name the devices that carry it, and you
   named none), and nothing is sent. Under **Devices that carry Mercury's management path,
   named by you** in the form, tick each device that carries it; each then goes last, alone,
   after every device reached through it, as a measured one does. One hash binds every device's
   program, its probe's program, the order, the devices you named, the options and the
   repository's commit.

## The run {#run}

2. `confirm`. **Deploy the canary**, as a verified person, confirms the hash once. The plan is
   made again with its options; a program, the order, an option or the repository that moved
   since refuses the run, naming both hashes, and nothing is sent.
3. `canary`. The canary alone, through the deploy's apply: held, its program recomputed and
   refused if it moved, sent merge-only, verified, then **probed** while still held: signed in
   AS the read-only account, its probe's program made again and refused if it moved (both
   hashes named), each AI read asked and each refused command tried, the record kept on its
   History. PASS (or INCOMPLETE: every read it could ask answered, every refused command
   refused) and it is saved to startup; a FAIL, the account not signing in, or a probe that
   cannot be made rolls it back before the save. Verify failing rolls it back too. With the pause chosen, the run then waits for **Continue the
   rollout**, your press, recorded; without it, it goes on by itself.
4. `waves`. Each wave in turn with no press, the settle waited before each, each device's
   program checked against the confirmed one before it is sent, then held, sent, verified,
   probed and saved as the canary was. The card draws where the run is and each device's state
   in place: waiting, deployed, verified and saved with its probe's verdict, failed and rolled
   back, or not started.
5. `management`. Each device that carries Mercury's management path goes last, alone, after
   every device reached through it, by itself like every wave.
6. `stop`. The first device that does not deploy, verify and pass its probe is rolled back
   (the pipeline's own rollback), the run stops, every device after it is named not started,
   and the team is told once, through the network's Who is told. **Preview the rollout
   again…** starts a new preview.
7. `record`. Each device's receipt, whatever happened, and its golden committed after its
   save, both on its History. The coverage reads again when the goldens are committed.

Every press needs a verified person: the confirm and a Continue are deploys. A server restart
loses a running or paused run's place (it is held in this server's memory): what it did is in
each device's History, and a new preview starts from what is committed.
