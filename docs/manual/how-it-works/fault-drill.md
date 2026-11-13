# Declare a fault drill

A fault drill is a fault you inject on purpose, to rehearse self-healing. You declare it on
the device BEFORE you inject it, so the incident it causes is known to be a drill from the
moment it opens. A drill is treated exactly as a real fault, with one exemption: the
per-device rate and the same-change guard do not stop it, so a fault can be rehearsed as
often as you want. Its heal is counted as a drill's, never in the real figures.

![Declaring a fault drill: you declare it before the fault, it is checked and recorded, and nothing is sent, silenced or held; the incident that opens on the device inside the drill is tagged a drill in the same write; every guard but 9 and 11, the verify and the rollback apply, and the heal is counted as a drill's.](diagrams/fault-drill.svg)

## Declaring it, step by step

Declare it on the device page, **Actions › Declare a fault drill…**, or on the host as Mercury's
user with `scripts/nmas-fault-drill <network> <device> --minutes 10 --expects "<the fault in
words>" [--script "<the injecting script and step>"] [--reason "<why>"]`. Both record through
the same writer.

1. **Check the declaration** (`check`). Read: the network and its inventory. Sent: nothing.
   Recorded: nothing yet. A declaration names one device of the network, the expected fault, a
   bound of 1 to 15 minutes (10 by default) and who declares it: a verified person on the
   device page, the host's login, labelled, on the host. On the device page the expected fault
   is a choice: one of the fix kinds the Self-healing tab's Fix kinds card lists (Missing line,
   Changed line, Added line, Admin down where intent says up, the link-down row and the rest),
   or **No fault (testing the drill itself)**, with an optional detail ("the EEM heartbeat
   applet on edge1"); on the host it is three words or more. Anything else is refused, naming what
   was given: a press with no fault chosen is refused at the choice itself, in the card, and
   nothing is recorded.
2. **Refuse a declaration after the fault** (`before`). Read: the network's incidents and its
   drills. Sent: nothing. Recorded: nothing. An incident already open on the device is named
   with its time and the declaration's: a declaration after the fault never makes it a drill,
   and there is no back-dating. A drill already open on the device is refused too: one at a
   time per device.
3. **Record the declaration** (`record`). Read: nothing new. Sent: nothing. Recorded: one row
   in the network's fault drills, append-only: its id, the device, the fault expected (in
   words: the choice and its detail, "Added line: an IPv6 route on edge1", with the choice and the
   detail kept beside them), from
   and until, who, how it was declared, the script and the reason. History draws it as "Fault
   drill declared". The card answers in place: "Declared: a drill on <device> until HH:MM:
   <the fault>. Inject the fault now; an incident on <device> before HH:MM is a drill."

## Ending it early {#end}

A drill lasts until its end unless you end it first. End it once its fault is healed, so a
later incident on the device is real again and a new drill can be declared on it. While a drill
is open on the device, its Actions menu offers **End the fault drill (until HH:MM)** in place of
Declare a fault drill…. It is one press, with no confirm: it sends nothing to the device and
only stops the drill's exemption early. On the host, as Mercury's user, run
`scripts/nmas-fault-drill <network> <device> --end`. Both record through the same writer.

- **Recorded:** one more row in the network's fault drills, naming the drill, who ended it and
  when. Nothing earlier is rewritten. History draws it as "Fault drill ended".
- **From the end on, an incident on the device is real.** An incident that opened before the
  end stays a drill: its tag was written when it opened, and nothing changes it.
- **Refused, naming what was compared:** a drill that is not declared, one on another device,
  one already ended (with when and by whom), and one already past its end. If the drills
  cannot be read, Mercury says so and neither ends nor declares one.
- **The answer is in place,** where the declaration's card draws its answer: "Fault drill
  fd-… ended at HH:MM; incidents from now are real." A refusal reads "Couldn't end the drill:
  <why>."

## What a drill changes, and what it does not {#exempt}

- **The tag is written when the incident opens,** in the same write: an incident whose device
  and opening time fall inside a declared drill is a fault drill. An incident on another
  device, or after the drill's end, is real, even while a drill runs. A device attached to an
  incident keeps its own tag.
- **Guards 9 and 11 do not stop a drill:** the rate per device (one heal an hour on a lab
  network) and the same deviation healed twice within 24 hours, which halts the network's
  policy. So the same fault injected three times inside an hour heals three times when each
  is declared; undeclared, the second is stopped.
- **Everything else applies to a drill exactly as to a real fault:** the kill switch, the
  mode and a halt; planned work; the approved state; the topology hold (a recent change on
  the device or its neighbours, a heal's own deploy included); many devices at once; a person
  working; the grace period; **guard 10, the rate per network**, which counts every heal, a
  drill's included; the program's size; a rolled-back heal; the tier; the verify and the
  rollback.
- **Counted as a drill, never in the real figures:** a drill's heal is not counted by guards
  9 and 11 for a real incident, nor in the dry run's Right / Wrong counts per fix kind. Its
  History row begins "Fault drill:" and names its declaration in its record.
- **The decision is the incident's tag, never the declaration read later:** a drill that
  expires or is ended changes no incident already tagged, and a declaration made later tags
  none.
- **A declaration silences nothing, holds nothing and sends nothing.** A drill's alerts fire
  and its rows are raised as a real fault's are.

## What it does not do {#not}

- It does not inject the fault: you do, after declaring it.
- It cannot be made after the fault, and it cannot be made for longer than 15 minutes.
- It is not a planned-restart window: it explains no restart and holds no Needs attention row.
