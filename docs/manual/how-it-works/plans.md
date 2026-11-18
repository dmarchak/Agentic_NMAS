# A plan of operations, approved once

![A plan of operations, approved once: the toolbar assistant may propose one of Mercury's plans with its parameters, which Mercury holds to the plan's schema; the preview shows every step previewed by its own operation, and one hash for the whole plan; you approve it with a reason; Mercury previews it again and refuses a moved hash, then runs each step in order through its own apply, verify and record; the first step that does not pass stops the plan, the steps after it do not run, and nothing is retried; the plan's outcome is recorded beside each step's own.](diagrams/plans.svg)

## Where it is

Ask the toolbar's **Assistant** for something one of Mercury's plans does, giving every value it
needs ("reserve 192.0.2.50 for printer-3, MAC 00:11:22:33:44:55, in subnet 20"). When its
answer names a plan, it says **Proposed:** with the plan's title, and **Preview the plan…** draws
the plan in place: each step previewed by its own operation, and the plan's one hash. A plan the
assistant names is only proposed. Mercury holds it to the plan's own schema first (a plan it has,
exactly its parameters, each of its shape); anything else is refused, and nothing is drawn.

## The plans

- **Reserve an address for a client in the network's DHCP**: one step, the DHCP reservation, as
  DHCP › Reservations makes it: its own preview (its checks, what it does not do), then, approved,
  written, Kea reloaded, read back from Kea and recorded in the Kea owner's repository. A network
  that uses another network's Kea is refused, naming both.
- **Describe a link at both ends in intent**: two steps, an interface's description set in each
  of two devices' committed intent, each as the Intent tab's edit makes it, on the version
  previewed, then read back. It deploys nothing: each device changes when its intent is deployed.

- **Add a device by ZTP**: one step, Add device's Create, as Devices › Add device makes it for a
  device by ZTP on **Mercury's own ZTP segment only**: its own plan (the hostname, platform,
  role, MAC, the address Mercury reserves and the domain), refused while Add device refuses it,
  naming why. A device behind a DHCP relay is not served by this plan yet: add it with Add
  device. Approved, Create holds the name, rebuilds its plan and refuses one that moved, then
  mints the device's one-time credential, commits its identity and intent, and writes its DHCP
  reservation; the device is then pending, and the plan ends "created and pending: Verify is
  its own approval", never green. **Verify is not in the plan**: it reads the device once it
  has booted and fetched its bootstrap, so what it does is not known when the plan is
  approved; it is its own approval, on the device's page. The one-time credential is
  Mercury's: minted at Create, never in a plan, never shown to the assistant.

## Intent changes and their deploys, in an incident's fix

An incident's fix is a plan too, approved on the incident's page. Besides Mercury's catalog
operations, its steps may be these two, each held to the incident's own device, to Mercury
being allowed to change that device, and to planned work, holds and windows on it (a step on
another device, or under one of those, is refused, naming it):

- **Change a device's intent**: any field intent models, given as changes, each a field's
  path (`interfaces.GigabitEthernet2.shutdown`), the value intent holds there now and the
  value it becomes. Each value now must be what is committed, and the changed document must
  pass the Intent tab's whole check, or the step is refused, naming the field and both values.
  The preview draws the change to the intent document and to its render, masked. Approved, it
  is committed as the Intent tab commits an edit, as you, with your reason, on the version
  previewed, and read back from its commit. It sends nothing to the device by itself. What it
  takes out of intent stays on the device after a merge-only deploy, and the step names each
  such line.
- **Deploy a device's intent**: the device's deploy, planned as **Deploy…** plans it. After an
  intent change in the same plan, it is planned from the changed intent, so the program you
  approve is the one that change will send: its hash binds that exact program and the captured
  config it was compared with, and the preview draws the program, masked. When the step runs,
  after the intent is committed, the program is planned again from what is committed; if it is
  not the one you approved (another commit landed, or the device's capture moved), the step
  stops, naming what moved and both hashes, and nothing is sent. Then it deploys exactly as
  Deploy… does: merge-only, held, verified, rolled back on failure, with its receipt. A line
  comes off the device only when the step names that line's removal (Mode B), and only where
  the removal's shape is measured; your reason at Approve is recorded as the reason for each
  line that needs one. A deploy that sends nothing, or would cut Mercury's path to a device,
  is refused.

The incident's page draws a fix holding these steps as it draws any other: each step checked
before it is drawn, in words, and everything its hash binds. A step that already ran in this
incident and failed is refused, naming that attempt, unless what it is compared by differs (an
intent change's changes; a deploy's removals and its program), which the step then names.
**Not built yet:** nothing proposes these steps yet (the AI's fix names catalog operations
only), so no screen offers them today.

## Saved plans: self-heal scripts and reusable actions

A command plan that ran and passed its own verify can be saved, its parameters left open:

- **As a self-heal script**, for one network: the plan, the problem it matches (only the
  classified problem's fields: its condition, cause, port role and whether the cause has
  cleared; never an alert's name or a raw line), and where each parameter comes from in that
  problem (the device from the problem's device, an interface from its object). It starts in
  **Dry run**: when an incident's problem matches, Mercury fills the parameters, previews the
  plan without asking the device, and records what it would have run on the script's own
  record. A person with self-healing rights promotes it; from then on, when it matches, it
  runs through the same runner, on that person's standing approval while they still hold
  self-healing rights (a promoter whose right was revoked authorises nothing, and the run
  is refused naming them), before the AI is asked,
  and an incident it heals says "Healed by saved script <name>: no AI used".
- **As a reusable action**, for every network: a named entry ("Bounce interface") that the
  catalog lists beside the plans Mercury ships, so it can be a step of a fix and the AI may
  propose it. Only an admin saves one.

**Who approves what.** Running a plan: any verified person. Saving or promoting a self-heal
script: a person with self-healing rights. Saving a reusable action, or adding a line's shape
to Mercury's rule for raw lines: an admin. Until the installation names who holds a right,
every verified person holds it. The AI may propose each of these and approves none.
**Where.** On an incident's page, at the foot of **Fixing it**, once a command plan has run
there and passed its own verify: **Save as a self-heal script** (tick the problem's fields it
matches on; the condition is always kept; how many open incidents it would match now is said;
each parameter is shown as it will be filled, a choice through a map you can read, and a
problem value the map does not name is refused by name when it fires) and **Save as a reusable
action** (its name and what it does). Below them, each saved script this incident's problem
matches, with **Promote <name>**, and the network's line shapes waiting on an admin, each with who
proposed it, why, and what its first run measured, with **Approve the shape**. A right you do
not hold is said beside its button, which is drawn disabled.

**Saving is the approval** (the operator, 2026-11-15). Once a fix verified, the incident's card
asks "Save this fix so Mercury handles it automatically?". **Save** saves it as a self-heal
script in **Automatic**, with the problem's name and its match ticked, promoted by you: it runs
when its match holds while the network's self-healing is on. **Customize…** holds the same form
with **Dry run** as a choice. **Not now** puts the offer off for this incident, saving nothing,
and the card then says so in one line with **Save this fix…**, which shows the offer again.
Every saved fix is listed on [Fixes](fixes).

**When a script fires.** After each self-healing decision that Mercury's own code cannot fix
(a can't-fix), and again before the AI starts by itself on an incident, every saved script of
the network whose match the incident's problem holds fires once for that incident, under
self-healing's mode: while self-healing is off, nothing; in Dry run, it records what it would
run; in Auto, an Automatic script runs, as a job of its own under **In progress** by
"Self-healing, saved script <fix> (approved by <person> at save)", and one in Dry run records.
Once one Automatic script has sent anything, the rest only record: one incident, one change. A
Manual only fix is never fired, only offered. A person's press (Start AI troubleshooting, Ask
the AI again, Modify…) fires none. A script never calls the AI. While it runs, its incident is
**Mercury working** with the run's step, and its verified run closes the incident Fixed
([Self-healing](heal#detect), step 8).

**What is already open when a fix is saved.** Saving a fix, or setting one Automatic, tries
again once each open incident that fix matches and that Mercury could not fix: standing on a
can't-fix, on a hold that no longer holds, or on a heal that did not heal. Each is sent back
for a fresh decision, every guard judged again on a fresh read, and the decision fires its
matching scripts, so in Auto the saved fix runs on it with no AI and no press. Switching
self-healing on does the same for every open incident, and every 24 hours while one stays
open. Each such retry is keyed by what started it (the save's own time, the switch-on's, the
day), recorded on the incident, and never made twice; nothing is retried while self-healing is
not in Auto. On the incident's own page, a matching fix is also offered to a person as **Fix
with saved script: <fix>** ([An incident's page](incident#bluf)).

**On a device's page.** A reusable action whose parameters one interface fills (a device and
an interface, as Bounce interface takes) is offered on the device's **Overview**, under
**Saved actions on an interface**: choose the interface, press **Preview <action>…** to read
what it sends and checks, asking nothing of the device, then **Run <title>**, bound to that
preview. It runs as a job, the device held, through the same runner as every command plan,
and its record is on History. Any verified person may run one.

**Not built yet:** a page of every network's waiting shapes, and the screen that sets who
holds each right. Every saved fix, with its record, is on [Fixes](fixes).

## Approve the plan

**Approve the plan on <network>: <title>** takes a reason of at least three words, recorded with
the plan and each step. You approve the whole plan once, by its hash, which names the network
it acts on: a plan previewed on one network is refused on another. Everything that hash binds is
drawn before you press: open **What its hash binds**, under the plan's hash line, for the
network, the plan, each of its parameters, each step's operation and parameters, what each
step's preview found (a reservation's subnet, from Kea) and each step's own hash. Who can approve it: a
verified person, as for any confirm. While it runs the card says which step it is on; a step
that broke while it ran is said as failed, whether it landed unknown, never as not run.

## The steps

1. `approve`: the plan is previewed again, every step by its own operation, and its hash compared
   with the one you approved. A plan that moved (a step's own preview changed, or refuses now) is
   refused, naming both hashes; nothing runs.
2. `step`: each step in order, `step-1`, `step-2` and so on. Each one's own preview is read
   again, and must be the one approved; then its own apply, which checks its own hash again, its
   own verify and its own record. **The first step that does not pass stops the plan**: the card
   says which and why, and the steps after it say they did not run. Nothing is retried: another
   try is another approval.
3. `record`: the plan's outcome, beside each step's own record, on History.

## What it ends with

The card in the assistant's panel draws the outcome first, then each step and what it did. A plan
stopped part-way leaves the steps before it done (each is its own operation's change, put right
as that operation's own is), and names the step that stopped it.

**What it never does.** No plan takes a secret, and the assistant never types one. The
assistant's plans send nothing to a device: each step is an operation that writes Mercury's own
records (Kea's reservations, committed intent). Only an incident's fix sends to a device, and
only through Mercury's own operations: a catalog operation, or a deploy of intent as Deploy…
sends it. The AI acts under its own identity, with an engineer's role: it may propose a plan
and draft an intent change, and it never changes a setting, a user or role, a credential or a
notification, and never approves anything. A plan the AI proposes holding a step a person
would take through one of those is refused before it is drawn, naming why. Add a device by ZTP's Create also commits the device's
identity and mints its one-time credential, which Mercury stores and never shows; it has no
rollback: **Abandon** on the device's page is its undo.
