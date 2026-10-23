# The model: intent, golden, device

{{product}} keeps three things about every device, and almost everything it does moves one of them
toward another. Learning which operation moves which is most of learning the tool.

## The three records

- **Intent** is what the device SHOULD be: a YAML document per device, committed to the
  network's git repository (`host_vars/<device>.yml`). A change is made by editing intent and
  committing it, never by configuring the device and copying what it has.
- **The golden** is what the device WAS, the last time the tool recorded it: its running
  configuration, captured and committed (`golden/<device>.cfg`). It is a record, not a wish.
- **The device** is what IS, right now. Nothing the tool stores can be trusted to equal it
  without reading it again.

![Intent, golden and device, and the operations that move each: a deploy moves the device toward intent; a capture moves the golden toward the device; seeding moves intent from the golden.](diagrams/intent-golden-device.svg)

Three operations connect them, and each moves exactly one record:

- **Deploy** moves the device toward intent (see [Deploy a change](deploy)).
- **Capture** (and its fleet form, Save All) moves the golden toward the device (see
  [Capture and Save All](capture)).
- **Seed** moves intent from the golden, once, for a device that has no intent yet (see
  [Seed intent](seed)).

## Which network you are looking at {#network}

The top bar names the network every page shows: **Network** and its name. Opening it lists every
network, your recent ones first, each with its mode in the picker's words ("the base" for
Default, "standalone", "inherits", "differs from Default", or "its settings cannot be read"),
and a box to find one by name. Choosing one opens the same kind of page
for that network, its address carrying `?list=`, so a copied link shows the same network to
whoever opens it; from a device's page it opens that network's Devices, and from a network's
settings it opens the chosen network's settings.

The choice is yours alone. It is remembered for you, as the verified person you signed in as,
and never moves anyone else's pages: two people can look at two networks at once. A page whose
address names a network shows that one, whatever you chose.

A page keeps the network it was opened on. Everything it does after it is drawn names that
network: each part it redraws when something changes, each row you expand, each button, each
link and each filter. So the label, the network the picker marks and what the page shows are
always the same one, and choosing another network in a second tab changes nothing on this one
until you open a page there again. If the network is deleted while its page is open, the label
reads **deleted** (its name on hover), and anything the page then asks for is refused, naming
that network: nothing on it is answered for another network. Choose a network to go on.

## What is running now {#in-progress}

An operation keeps running when you leave its page, so the top bar of every page says what is
running and what finished while you were elsewhere. With nothing running and nothing waiting
for you, the top bar shows nothing. Otherwise it shows the **In progress** chip:

- **"2 running"** (blue, with a dot): operations running now, in every network, by anyone.
  Opening the chip lists each one: the device, the operation, the step it is on (in its
  stepper's own words, "step 6 of 6"), who started it, and since when; one that has made no
  progress for too long carries a red "no progress: may be stuck". **Open its card** opens
  the device's page, which shows that operation's card where it runs; a console run (an
  out-of-band onboarding, a console survey or kick-start) has **Open its stepper**, its own
  page, since a device being onboarded may have no page yet. Devices draws the same list above
  its device list while anything runs; an operation that holds
  no device (a NetBox preview, a Save of many devices) is listed without one. A device being
  onboarded is listed too, as **Onboarding: waiting for it**, from its Create until Verify or
  Abandon ends it, with where it has got to ("leased not fetched", "answering: ready to
  Verify"); **Open <device>** goes to its pending page.
- **"In progress unread"** (or a count marked **unread**): the tool could not ask which
  operations are running, or could not read what runs in a network. It says so, and that this
  is not the same as none running: an operation may be in progress there.
- **A cross, a warning sign or a tick, with a count**: an operation a device's page started
  that finished while you were elsewhere, with its outcome in its card's own words. Red wins:
  one failed operation makes the chip red, a partial one amber, and it is green only when every
  finished one is clean. **Open the result** opens the device's page on that result. Once you
  have seen a result (on its card, or on the device's page), the chip stops listing it for you,
  and only for you: someone else who has not seen it still has it on their chip.
- **Unread**: the tool could not read what runs in a network. That is not the same as nothing
  running there, and the chip says which network and why.

The chip reads again the moment an operation starts or finishes, at each step, and when a
device is released, over the live connection; it never asks on a timer. A finished result is
kept for 30 minutes, in the running app's memory: after that, or after the app restarts, it is
in History (All recent operations), and a state an operation left behind (a rotation not yet
persisted) is a Needs attention row.

A device's page opened while that device has an operation running, or one finished you have
not seen, opens THAT card in place of its tab, wherever you came from: the chip, a bookmark or
the Devices list. A card that was refused because another rotation held the device shows that
rotation's result when it ends, never a fresh offer to rotate again.

## Everything is read from what is committed

Every reader takes intent and goldens as COMMITTED in git, never a file edited on the host's
disk. A file nobody committed governs nothing, so the record you can see in History is the
record the tool acts on.

## Merge, not replace

A deploy ADDS the lines intent has and the device lacks, and changes nothing else. A line the
device has and intent lacks is reported as residue and left in place. Removing a line is its
own operation, chosen line by line (see [Remove a line (Mode B)](removal)).

![Merge versus replace: a merge sends only the lines intent has and the device lacks, and leaves the device's other lines in place; a replace would remove every line intent does not name, which {{product}} never does.](diagrams/merge-and-mode-b.svg)

## Preview, confirm, result

Every operation that changes a device or the record works the same way:

1. **Preview.** The tool computes exactly what it will send and record, reading what it needs
   now, and shows it: the program, the gates it checked, and what it will NOT do.
2. **Confirm.** You confirm that preview. The confirm is bound to a hash of what you saw: if
   anything moved between the preview and the confirm (the device, intent, a template), the
   tool refuses and sends nothing, and you preview again.
3. **Result.** What happened, device by device, drawn from the record the operation wrote,
   so you can find it again later in History.

A button that asks for something says so on itself from the moment you press it: it greys out
and its words change to what is running (**Starting the dry run…**, **Probing…**,
**Approving…**) until its answer is drawn in place, and then it is itself again. While it says
it is working it cannot be pressed a second time, so one press starts one run.

Nothing you click goes quiet. When an answer cannot be drawn (the server refused without a
card, did not answer, or answered with nothing for that place), the place it would have
appeared says what could not be loaded, for example **Couldn't load the 6-hour view.**, and
keeps what it showed. Point at the words for the technical reason; **Try again** asks once
more. The notice sits in that place, below the control you used, so the control itself never
moves.

Every page also checks that it arrived as the tool sent it. If something between the tool and
your browser added scripts (a proxy rewriting pages, or a browser extension), the top of the
page says **This page arrived changed**, names each script, and says what to turn off.

## A baseline is a moment

A baseline tag (`baseline/<time>`) names one commit at which every device's golden and
intent were recorded, and says what that moment EARNED: whether every device was measured at
its committed intent.

![What a baseline contains: one commit holding every device's golden and every device's intent, named by the tag baseline/<time>, with what it earned recorded on the commit.](diagrams/baselines.svg)

Re-applying a baseline sends each device what it lacks from that moment (see
[Restore and re-apply a baseline](restore)). Credentials are always the ones held NOW:
a baseline older than a rotation would otherwise put back a password the rotation retired.

## Who did it

Every commit carries an `Actor:` and how that actor was established
(`Actor-Verified: access` for a person signed in through the tunnel, `host-shell` for a
command run on the host, `none` when neither could be established). Anything that changes a device or exposes a secret has a person
behind it.
