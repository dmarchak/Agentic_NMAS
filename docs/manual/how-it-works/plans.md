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

## Approve the plan

**Approve the plan on <network>: <title>** takes a reason of at least three words, recorded with
the plan and each step. You approve the whole plan once, by its hash, which names the network
it acts on: a plan previewed on one network is refused on another. Who can approve it: a
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

**What it never does.** No plan takes a secret, and the assistant never types one. No plan sends
anything to a device: each step is an operation that writes Mercury's own records (Kea's
reservations, committed intent). Add a device by ZTP's Create also commits the device's
identity and mints its one-time credential, which Mercury stores and never shows; it has no
rollback: **Abandon** on the device's page is its undo.
