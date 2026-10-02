# Merge-only, and Mode B

Every deploy and every restore is a merge: the tool sends the lines intent has and the
device lacks, each inside its section, and nothing else. A line the device has and intent
does not mention stays where it is. Removing a line is a separate decision, made by a person
one unit at a time, and only for line shapes the tool has measured on that platform. That is
Mode B.

![Merge-only and Mode B: the merge sends only the lines intent has and the device lacks, each inside its section; residue stays on the device; a person may tick a residue unit for removal, and only a shape measured on the platform is sent, as the device's own line with no in front, at the end of the program.](diagrams/merge-and-mode-b.svg)

## What a merge sends {#merge}

The tool compares the render of intent with the device's capture, line by line, and each
line is keyed on its section as well as its text: ` shutdown` under one interface is a
different line from ` shutdown` under another. Every line on the intent side falls into one
of three kinds:

- **add**: nothing on the device sets this. It is sent.
- **replace**: the device sets the same thing to another value (a different description, a
  different timer). The new line is sent, and the device replaces the old value itself.
- **residue**: a line on the device that intent does not mention at all. It is not sent,
  not negated, and is listed in the preview under its section, saying it will NOT be
  removed.

The program is exact: each added line is preceded by the headers of its section, in order,
and each group ends with one `exit` per level it opened. It never contains `end`. What you
confirm is this list, byte for byte; it is computed again at apply and refused if it moved.

A residue line that shares a setting with a line intent already has on the device (one
setting with two spellings) is named as such in the preview, because it is neither replaced
nor plain residue.

## Why the tool never removes by default {#why}

- **`no <line>` can remove more than the line.** On some platforms negating one entry of a
  numbered access list deletes the whole list; negating some settings turns a feature off
  instead of restoring its default. A tool that synthesised negations would destroy
  configuration nobody chose to touch.
- **A line intent lacks may be what is keeping the network up.** A change made by hand
  during an incident is residue until someone decides. Removing it automatically would
  decide, for the person, which side of that departure is right.
- **The rule is checked by provenance, not by spelling.** Before anything connects, every
  added line must appear verbatim in the render of intent. A template may legitimately
  contain a `no` line (`no ip http server` is real configuration); what the check refuses is
  a line the tool made up.

The only place the tool composes a negation on its own is a rollback, undoing exactly what
the push added, and that undo is itself checked against what was pushed.

## What merge-only costs {#cost}

Residue is permanent in the record until a person removes it. While it remains:

- the device departs from its intent, so a Save All records `Intent-Match: no` for it and
  earns no baseline (see [How a baseline is earned](baselines));
- a restore that leaves residue is not at the chosen moment, so it earns no baseline either.

There are two ways out, and they mean opposite things: adopt the line into intent (it was
right), or remove it from the device with Mode B (it was wrong).

## Mode B: a person selects each removal {#mode-b}

The deploy preview lists the device's residue, and each item is a unit with a box:

- **A line** (a leaf): one residue line, inside its section.
- **A stanza**: a section whose header intent lacks, offered as one unit with its lines
  listed. Removing the header removes them. A physical interface is the exception: its
  header cannot be removed, so it is shown refused, and each line under it is offered on its
  own.

Ticking a unit asks for your reason, and that is the one decision: the tick chooses it, the
reason says why. The reason is bound into the confirm hash and kept in the receipt. A unit is
selected by an identifier, not by its text, so a line in a secret position (an old SNMP
community, for instance) can be selected although the preview shows it masked.

The removals ride at the end of the deploy's program: the merge's additions first, then any
re-created IP SLA operations, then the removals. See [Remove a line (Mode B)](removal) for
the run itself.

## Only shapes measured on the platform {#measured}

A unit is removable only if its line matches a SHAPE that was measured on the device's
platform, on a throwaway device, to remove exactly that line and nothing else. The shapes
include an interface's `load-interval` and `description`, `logging host`, an
`snmp-server community`, a prefix-list entry, a route-map sequence, a named access-list
entry, an event-manager applet, and `cdp run`. Each platform has its own measurement, and
each result is one of:

- **removes exactly that line**: the only result that allows a removal;
- **removes MORE than that line**, **changes other configuration**, **does not remove the
  line**, **leaves the device off its default**, **is rejected by the device**: each refuses,
  quoting the measurement (which device, when, what happened).

A line no shape covers, a shape not yet measured on this platform, a device whose platform
is not known, and a measurement record that cannot be read all refuse, naming why. The
measurements are taken by `scripts/nmas-removal-probe`, and the refusal names the command
that would measure the shape. The list is an allowlist: a line added to the device later
cannot outgrow it.

## Refused whatever was measured {#refused}

Some units are refused before the measurement is consulted, each with its reason beside the
box:

- **IOS will not remove it**: the hostname, the version line, the boot markers, a `line`
  stanza (change its settings instead), a banner, a certificate or trustpoint, and a
  physical interface (resetting one is `default interface`, which is not built).
- **A numbered access-list entry** at the top level: `no access-list <n> ...` deletes the
  whole list.
- **The management path**: the interface the tool reaches the device on (or one addressed
  by DHCP), the vty lines, SSH, AAA, the RSA key, the domain name the key depends on, a
  static route and the default gateway. A rollback would travel over the thing being
  removed.
- **An account** (`username`, `enable secret`): removing one is rotation's or retirement's
  job, never a residue clean-up.
- **A named object still in use**: a prefix-list, route-map, access list, VRF or key chain
  that another line names. The reason quotes the line that uses it; remove or change that
  first.
- **`logging buffered`**: measured to turn buffered logging off and leave `no logging
  buffered` behind, a state neither the device nor intent names.

## The removal is the device's own line {#verbatim}

The command sent is `no` followed by the device's own line, verbatim, inside its section. A
rebuilt line would drop an access list, a view or spacing the device has, and then it would
not match. A line that is itself a `no` line is removed by sending its positive form.

After the push, verify reads each removed unit back and fails if it is still there. The undo,
if the deploy rolls back, is never a second negation: it re-adds the device's own lines from
the snapshot taken before the change, and refuses to send any line that snapshot did not
hold.

## What Mode B does not do

- It never converges a device to intent. Nothing is removed that a person did not tick.
- It never sends `default <command>` to restore a platform default.
- It does not remove anything on a platform where that shape has not been measured, even if
  the same shape is allowed on another platform.
