# Drift

Drift is a difference the tool did not make: the device runs something its record does not
say it runs. This page says what the tool compares to find it, what it deliberately does not
count, and the two ways to resolve it, which mean opposite things.

![The three records and the comparisons between them: the device against its golden is drift (the drift check); the golden against intent is a departure from intent (every capture); the device against intent is what a deploy plan would send.](diagrams/drift.svg)

## Three records, three comparisons {#comparisons}

The tool keeps intent and the golden for every device, and the device itself is the third
record (see [The model: intent, golden, device](getting-started)). Each pair answers a
different question:

- **The device against its golden** is *drift*: the device changed since the tool last
  recorded it. The [drift check](drift-check) asks this on a schedule, and the device page's
  Drift row shows its last answer.
- **The golden against intent** is a *departure from intent*: what the tool recorded is not
  what the device should be. Every capture computes it, every golden commit carries it as an
  `Intent-Match:` trailer, and the device page's Intent row shows it.
- **The device against intent** is what a deploy would send. A [deploy plan](deploy) splits
  its lines into the ones your edit asked for and the ones already pending before it: the
  second kind is drift the last capture had not seen.

A device can be clean on one comparison and not on another. A device at its golden can still
depart from intent, and a device whose drift check is clean says nothing about intent at all.

## What counts as drift {#what-counts}

The drift check compares the running configuration with the committed golden, line by line,
in order. Before comparing, it removes from both sides the lines that change with nobody
changing anything:

- blank lines and lines that are only `!`;
- the banner a read starts with (`Building configuration`, `Current configuration`);
- the change and save comments (`! Last configuration change`, `! NVRAM config last updated`,
  `! No configuration`);
- `version`, `ntp clock-period` and `upgrade fpd` lines;
- the device's own self-signed certificate (below).

Everything else is drift, including a line that only moved: the comparison is ordered.

## A regenerated self-signed certificate is not drift {#certificate}

A device with secure HTTP or RESTCONF on makes its own self-signed certificate
(`crypto pki trustpoint TP-self-signed-<digits>` and its certificate chain), and makes a new
one when it boots without one. The new one has a new body and often a new trustpoint name,
with nobody having changed the configuration.

So the comparison removes the device's own `TP-self-signed-<digits>` stanzas from both sides,
and says in one line that the certificate was regenerated instead of drawing its hex. Only
that trustpoint is removed: a CA-signed trustpoint is configuration somebody chose, and a
change to it is real drift. The golden itself still records the certificate verbatim.

## What drift is not {#not}

- **Not a judgement of which side is right.** The check finds a difference; it cannot know
  whether the device or the record is the one to keep.
- **Not a departure from intent.** The drift check never reads intent.
- **Not timed.** A drift row says when the check saw the difference, never since when it has
  existed.
- **Not fixed by anything automatic.** Nothing resolves drift without a person confirming a
  preview.

## Two ways to resolve drift {#resolve}

Each way moves one record toward the other, and each asserts something different. Both are on
the device page.

1. **Capture the running config as the golden** ([Capture and Save All](capture)). Asserts:
   *the device is right, and the record was behind it.* The device is read now, the change is
   previewed against the golden and against intent, and the confirm records it as you.
   Capturing a change nobody made on purpose makes it part of the record.
2. **Restore the device from its golden** ([Restore and re-apply a baseline](restore)).
   Asserts: *the record is right, and the device moved away from it.* The golden is re-applied
   through the deploy path. It is merge-only: it sends back lines the device lost or changed,
   and a line the device gained is reported as residue and left in place. Removing it is its
   own operation ([Remove a line (Mode B)](removal)).

Approving a queued drift item opens the capture preview for that device: it is the first way,
still previewed and still confirmed, never a shortcut.

## Resolving a departure from intent {#resolve-intent}

When a capture or the device page shows the golden departing from intent, the tool names the
ways out and what each asserts. It never offers one as a single click.

- **A line on the device that intent lacks:**
  - *Remove it from the device* (Mode B, ticked in the deploy plan with a stated reason, then
    capture). Asserts the device is wrong and intent is right. Sent only where the platform
    was measured to remove exactly that line; otherwise the plan refuses it, naming why, and it
    is removed by hand.
  - *Adopt it into intent* (edit intent and commit the line). Asserts the device is right and
    intent will deploy it from now on. A deliberate edit: a hand change adopted by reflex
    becomes what the tool calls intended.
- **A line intent has that the device lacks:**
  - *Deploy it.* Asserts intent is right and the device is behind it.
  - *Remove it from intent* (edit intent). Asserts the device is right and intent was wrong.
