# The installation's settings: save, test, replace a token, turn NetBox writes off

The installation's own settings apply to every network, standalone ones included: the central
NetBox, Proxmox, the author line of Mercury's commits and this host's address. They are on
**Settings › Installation**: the **NetBox connection**, **Proxmox** and **Commit author** cards
on the Connections tab (beside the records database, which has its own page), and the
**Server** card on the Server tab. Nothing here contacts a device.

![An Installation card. Save checks each field, writes the ones that changed to the installation's settings for every network, and appends who, when and which fields to the installation's settings record. Test asks the service now with what is saved. Replace stores a new token as a secret, records it and tests it. Turn off writes NetBox's master switch off and records it; turning it on is the confirm of an authorised NetBox write. No device is contacted.](diagrams/installation-settings.svg)

Each card's badge is the service's health as the integrations reader last stored it (it asks
every minute; hover for its message): **reachable**, **not answering**, **refused**, **not
configured**, or **not read yet** when the reader has stored nothing. The page never asks a
service itself; **Test** is a person asking now.

## Save {#save}

**Save** writes the card's fields. A switch left unticked is saved as off.

1. `check`: each field is checked against its kind. Read: nothing else. Sent: nothing.
   Recorded: nothing. An address must start `http://` or `https://`; a node, storage or
   other name is letters, digits and `. _ -`; backup VMs are numbers separated by commas; a
   date is `YYYY-MM-DD` or empty; the port is a number from 1 to 65535. A refusal names the
   field and what it accepts, and nothing is saved.
2. `write`: only the fields that changed are written, to the installation's settings, for
   every network. Read: the settings as they stand. Sent: nothing. Recorded: the values.
   Saving what is already stored writes nothing and says "Nothing changed".
3. `record`: the save is appended to the installation's settings record, a file. Read:
   nothing. Sent: nothing. Recorded: who, how that was established, when, the card and the
   names of the fields written, never their values. If the record could not be written the
   card says so; the save is made either way.

The **Server** card's bind address and port are read when Mercury starts: its Save says the
change waits for the next restart, and Mercury listens where it did until then. The TFTP root
is not on this card: it is read only by today's device file pages, which are removed at
cutover, so it leaves with them (Mercury's own transfers serve their files from memory).

## Test {#test}

**Test** asks the service with the settings as saved (save first: it tests what is stored, not
what is typed), and changes nothing. NetBox is asked for its status and answers with its
version; Proxmox is asked for its version with the token. The answer is drawn in the card: the
version on success, the service's own words on failure (a refused token, a certificate that
does not verify, nothing listening). The badge stays the reader's and catches up within a
minute.

## Replace a token {#replace}

A token shows only as set or not set: it is never drawn back. **Replace…** opens in the card.
NetBox takes the new API token; Proxmox takes the token's id and its secret together, since a
Proxmox token is the pair.

1. `check`: the new token is not empty and holds no space or character a token never has;
   Proxmox's id has the form `user@realm!name`. Read: nothing. Sent: nothing. Recorded:
   nothing. A refusal replaces nothing.
2. `store`: the token is stored in the secrets store, encrypted (Proxmox's id in the
   installation's settings first). Read: nothing. Sent: nothing. Recorded: the token,
   encrypted.
3. `record`: the replace is appended to the installation's settings record. Recorded: who,
   when and the names of what was replaced, never the value.
4. `test`: the card's Test runs at once with the new token, and its answer is drawn.

Make the new token in NetBox or Proxmox first, then replace it here, then remove the old one
there once the Test passes.

## Turn NetBox writes off {#writes-off}

**Writes allowed** is the master switch for every network's NetBox writes. Mercury writes to
NetBox only while it is on, and only as an authorised operation a person confirmed. Turning
it on is that confirm's, with writes permitted, once the operation's token and plan both
pass; never this card's.

1. `write`: the switch is written off in the installation's settings. Read: the switch.
   Sent: nothing. Already off: nothing is written and the card says so.
2. `record`: who and when are appended to the installation's settings record; the card shows
   them beside the switch while it stays off.

There is no confirm step: turning writes off takes nothing away a person must keep. An
operation that needs NetBox writes afterwards asks for its own confirm, which turns the switch
back on.

## Diagnostics: redaction {#redaction}

Every line Mercury logs is masked as it is written, by a filter on every log handler. The
**Redaction** card asks whether that works now: it builds a test record holding secret-shaped
lines (a canary) and runs it through each handler's filters without writing it anywhere, and
counts the handlers with no filter and the redactions that failed since start-up. **Check
again** asks again; it writes nothing. Not healthy, it is also a row on Needs attention naming
the handler and what got through: every handler gains its filter when Mercury starts, so a
restart is the remedy, then a read here to see it healthy.

## Diagnostics: drift checks {#drift}

Mercury compares each device's running configuration with its golden on a schedule, one for
every network; what it finds is on Needs attention. The **Drift checks** card sets the schedule
and shows each network's state, its last run and its next.

1. `check`: the schedule must be one of the seven offered (30 minutes to 24 hours); a network
   turned off or on must exist. A refusal names what was sent and what is allowed.
2. `write`: the schedule is written to the agent's timers and the checker re-arms; a network's
   switch is written to its drift state with who and when.
3. `record`: who, when and what changed are appended to the installation's settings record.

**Check now** starts a network's check in the background (the schedule would run it anyway,
only later) and is refused while one runs; the card redraws when the check records its
result, and what it found is on Needs attention.

## Diagnostics: in flight {#in-flight}

The **In flight** card lists every network's held devices and running operations, each with
who, its current step and how long it has held the device (a step quiet for too long reads
stalled), and, folded, what finished in the last half hour, from the receipts. It redraws when
a hold or a step moves. It is a read; **Read again** reads it now.

## Diagnostics: the app's log {#log}

The **app's log** card shows the last 200, 500 or 2000 lines of Mercury's own log, filtered by
what a line contains, read when asked and never polled. Every line was masked as it was written
(the redaction above); nothing here unmasks one. A log not written yet and one that cannot be
read are said differently.
