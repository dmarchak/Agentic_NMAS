# Fixes

**Fixes**, under **Troubleshooting** in the sidebar, lists every fix the network the page is
about has: the fixes saved on it (and those shared with every network), and Mercury's built-in
fixes. Each one opens its own page, which says what it sends, what it checks, where it came from
and what it has done. Opening either page starts nothing and changes nothing; nothing on them
acts on a device until a person presses **Run on <device>** inside **Run…**.

How a built-in fix runs comes from Mercury's code and the network's own settings, never typed:
a self-healing fix kind runs by itself only where the network's fix kinds to heal name it
(Automatic); one not named records what it would do (Dry run); the telemetry re-subscribe and
re-add are a person's operations (Manual only). How a saved fix runs is its own mode.

## The list {#list}

A summary line first: how many fixes, how many saved (by how each runs) and how many built-in,
and, when any saved fix was deleted, a link to them. Then one table, each row a fix:

- **Name**, which opens the fix's page (**Shared** beside a fix saved on another network and
  shared with every network);
- **Mode**: Automatic, Dry run, Manual only or Off, its reason on hover;
- **Source**: Mercury built-in, AI (the AI proposed it and a person saved it) or Person;
- **Fixes**: the problem it fixes;
- **Runs**: how many times it ran and how many verified (for a fix kind, how many times it
  healed and how many dry runs it recorded);
- **Last run**, in your own time zone.

The table is drawn in Mode order, Automatic first, then by Last run, newest first. Pressing a
column's header sorts by it; the sort is kept in this browser only. The list draws its first 100
rows and counts the rest. **Search or filter…** narrows it on the server to words (a name, what
it fixes, a device), a way it runs, and saved, built-in or deleted; **Show** applies them. A
deleted fix shows only under the Deleted filter. The list redraws itself when a fix is saved,
changed or run.

## New fix… {#new}

**New fix…** draws its form in place, above the list. Every choice in it comes from Mercury:
what it fixes from the problem's own fields (a condition, a cause, a port role, and whether
Mercury reads the cause as cleared; how many open and closed incidents it would match is said),
each line one of the shapes known to undo itself in one batch (**Add a line…** adds one; another
shape is provisional until an admin approves it: a person's **Run…** sends it, an Automatic
fire refuses it, naming the shape, and sends nothing; and one that would last is refused), each
check before and each verify after one that Mercury's plans hold. The form draws a preview of
what it would send on an example as a choice changes. Saving it saves the fix as **Manual only**:
it runs when a person presses **Run…**, and can be set Automatic after its first verified run.
**Cancel** closes the form, saving nothing. Nothing in the form reaches a device.

## A fix's page {#fix}

The page leads with the fix: its name, what it fixes, how it runs and its record, **Run…**, and,
for a saved fix, **Saved from:** the incident it was saved from. Then four folded sections:

- **Contents**: what it sends, in config mode and never saved; the checks it reads first, each
  of which refuses the run when it fails; what it verifies after, a failure rolled back; and
  its versions, each kept. **Edit…**, for a saved fix, draws the same form as New fix… in
  place: a change to its name, description or match saves in place, the same version (its
  save's hover: **Saves the name, description and match in place, the same version**); a change
  to its lines, checks or verify saves a new version, the old one kept with its runs, and an
  Automatic fix returns to Manual only until the new version has a verified run.
- **Origin**: where it came from and when.
- **Record**: each run, newest first, with its version, who ran it and what it did, and Open
  the run; every run is also on [History](history).
- **How it runs**: the ways a fix runs, this one's marked, what changed it and when, and what
  its checks cannot prove on a port that is down.

A built-in fix's page is read-only, but a built-in command plan has the same **Run…** as a
saved fix.

## Run… {#run}

**Run…** draws its card under the lead. **Run on an open incident**: the open incidents this
fix matches; picking one fills the device, the port and the cause from its problem. **Or choose
a device and interface…**: a device and an interface from committed intent, and each choice
the plan takes; **Or run on an open incident…** goes back to the incidents. Neither reads a
device to draw the card. The card shows exactly what it sends, its checks and its verify; the
device is held while it runs, and a failed verify is rolled back. **Run on <device>** runs
exactly that preview, bound to its hash, through the incident's or the device's own run path,
and the answer is drawn in the card, with Open the run. A fix no open incident needs says so in
one line, "No open incident needs this fix right now", with no device, no interface and no Run
button; **Or choose a device and interface…** beside it opens the device path when you ask for
it. **Cancel** or **Close** closes the card, sending nothing.

## Set Automatic, Delete and Restore {#how-it-runs}

Inside **How it runs**, for a saved fix:

- **Set Automatic…**, after the fix's first verified run (or its new version's): **Set
  Automatic** makes it run by itself on a matching incident while the network's self-healing is
  in Auto, on your standing approval of this version's plan. It needs self-healing rights.
- **Delete…** takes a reason, then **Delete this fix**: the fix is no longer offered, matched or
  run, and leaves the AI's catalog; its record, origin and runs are kept here and in History.
  **Restore…** with a reason, then **Restore this fix**, brings it back as it was.

Each answer is drawn in place; a right you do not hold is said beside its button, which is
drawn disabled.
