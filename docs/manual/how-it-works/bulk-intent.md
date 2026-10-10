# Edit intent in bulk

Bulk intent makes one change to many devices' committed intent, as one commit. The change
is a list of settings, each with the value it must hold now and the value it becomes. A
device whose intent does not hold the expected value is refused and named, so a device that
has drifted from the others is never edited blindly. It changes intent only; the devices
change when you deploy.

![A change file names settings with their value before and after. Each device's committed intent is compared, refused devices are named, the accepted ones are rendered and grouped by what changes in their configuration, and one commit records them all. No device is reached.](diagrams/bulk-intent.svg)

## Where it is {#where}

On **Devices**, tick the devices, open **Actions** and choose **Change a setting on (N)…**.
The page names the devices and asks for a one-line summary (it becomes the commit's subject)
and each setting: its path, the value it holds now, and the value it becomes, written as in
the intent file (`514`, `true`, `[a, b]`, `{level: informational}`), or `(absent)` for a
setting not there, or to remove one. **Add a setting** adds a row. **Preview the change** runs
[the preview](#the-preview) below and draws it in place: the counts first, the refused devices
with each reason (and, where the before-state differs, the value expected and the value held),
then the accepted devices grouped by what changes in their configuration, each group collapsed,
with what a deploy would send, what is no longer rendered, and each device's intent diff.
**Commit the change to N devices' intent** needs a verified person and is bound to that
preview; the result names the commit and offers **Plan a deploy for these N…**, for exactly
the devices it changed.

The same code runs on the host as `scripts/nmas-bulk-intent`, and behind its two JSON routes,
which also accept a confirm only from a verified person.

```
nmas-bulk-intent --list <list> --devices <a>,<b>,<c> --change <change.json>
nmas-bulk-intent --list <list> --devices <a>,<b>,<c> --change <change.json> \
    --apply <preview hash> --actor <you>
```

## The change {#change}

A change file holds a one-line `summary` (it becomes the commit subject) and a list of
`steps`. Each step is a `path` into the intent document, a `before` and an `after`. Paths
use the same keying as a revert: dictionary keys, and list items that carry a `name` are
keyed by that name (an interface by its name). Use `{"__absent__": true}` as `before` for a
setting that is not there yet, or as `after` to remove one. A setting the change does not
name is never touched.

## The preview {#the-preview}

1. **Check the change itself**. Read: the change file. Sent: nothing. Recorded: nothing. A
   path the intent schema does not know refuses the whole change before any device is
   read: that is a typo in the change, not a fact about a device. A change with no steps is
   refused too.
2. **Check each device can take part**. Read: the list's inventory and the pending
   onboardings. Sent: nothing. Recorded: nothing. A device not reached yet, or not in this
   list's inventory, is refused and named.
3. **Read its committed intent**. Read: the device's intent at HEAD, never the working file.
   Sent: nothing. Recorded: nothing. A device with no committed intent is refused.
4. **Compare the before-state**. Read: each step's path in that intent. Sent: nothing.
   Recorded: nothing. Every step whose current value differs from `before` is listed with
   the value expected and the value held. A file that is hand-formatted is refused too,
   because writing it would silently drop its comments or layout. All of a device's
   reasons are given at once.
5. **Apply the steps and check the result**. Read: nothing more. Sent: nothing. Recorded:
   nothing. The new document must pass the same checks a hand edit does: the syslog block
   whole or absent, no unknown interface key, no description that is a run's notes (the
   tool's "NSoT-managed - " prefix, "smoke", "check", a course code: C428), printable
   characters only, no secret value.
   A device whose result would be refused is named with why.
6. **Render before and after**. Read: the device's captured configuration and its template,
   with the monitoring profile merged in. Sent: nothing. Recorded: nothing. Both intents are
   rendered and compared line by line, each line under its section. A result that does not
   render is refused. A device whose result renders but is not deployable is accepted, and
   the reasons are shown as a note.
7. **Group by effect**. Read: nothing. Sent: nothing. Recorded: nothing. Devices whose
   configuration changes by exactly the same lines form one group. The headline reads
   "N device(s), K group(s), M refused", and the preview prints a hash of every accepted
   device's current file and new text, the refused set and the steps.

Read the headline before applying. One group means the change does the same thing on every
accepted device; a second group means it does something different somewhere, and the
preview shows exactly what.

## The apply

1. **Require a summary**. Read: the change file. Sent: nothing. Recorded: nothing. With no
   summary there is no commit subject, so nothing is done.
2. **Compute the preview again and compare**. Read: everything the preview read. Sent:
   nothing. Recorded: nothing. A hash that differs from the one you give is refused naming
   both, with nothing written: a hash from another preview, a typing slip and intent that
   moved since all read this way.
3. **Refuse when nothing is accepted, or the intent folder is not clean**. Read: git's
   status of the intent folder. Sent: nothing. Recorded: nothing. An uncommitted change to
   any intent file refuses the apply.
4. **Write and commit** (`Source: bulk-intent`). Read: nothing. Sent: nothing. Recorded: the
   accepted devices' intent files and ONE commit of exactly those files, as you (or the
   `--actor` on the host), with an `Operation:` trailer holding the steps and a `Refused:`
   trailer naming the devices left out. If the commit fails, every file written is put back
   as committed and the result says nothing changed.

Each device's change can still be reverted on its own later: a revert reads and writes one
device's intent. See [Revert or retry after a rollback](revert-retry#revert).

## What it does not do {#not}

- It sends nothing to any device. Deploy afterwards; the batch deploy is in
  [Deploy a change](deploy).
- It never edits a device whose current value differs from `before`, and never edits around
  a refusal. A refused device is named and left exactly as it was.
- It never invents an interface: a path through a named list item that does not exist is
  refused for that device.
- It does not apply a change to devices you did not name.
