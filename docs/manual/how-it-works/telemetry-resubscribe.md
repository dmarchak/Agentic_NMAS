# Re-subscribe a lost telemetry stream

A device streams telemetry by dialling out to its collector, one session per receiver. When
that session goes stale (the collector's side was cancelled, the device still reads its
receiver Connected and never dials again), the stream stays lost after its cause is gone.
Removing the subscription's receiver and adding it back makes the device dial again. This
operation does that, with each receiver line taken from the device's committed intent, and
then checks each stream is back. With several subscriptions ticked it removes every ticked
receiver first, then adds each back: a device's subscriptions to one receiver share one
connection, so one left in place keeps the old connection open and the others rejoin it. Its
configuration ends exactly as it began, and nothing is saved to startup.

![Re-subscribe a lost telemetry stream: the plan reads each subscription's receiver from the device's committed intent and refuses one whose removal is not measured; you tick the subscriptions and confirm with a reason, each bound to its hash and the selection to its own; holding the device, the run is recorded before anything is sent, then each receiver's state, the collector's sessions and the configuration are read; every ticked receiver is removed, one after the other, the read-back after each showing exactly the lines removed so far gone; ten seconds pass, once; each is added back, once more if it did not land, and the configuration must read as before; then for each subscription the device's receiver on a new connection, the stream's data in Prometheus and a new session on the collector are read for up to 290 seconds; a receiver that did not come back is said, with Re-add the receiver; the run is recorded with each subscription's own outcome, and History shows it. Nothing is saved to startup.](diagrams/telemetry-resubscribe.svg)

## Where it is

On **Needs attention**, a row "<device>: telemetry stream lost" (or "<device>: 2 telemetry
streams lost (101, 102)") carries **Re-subscribe <device>'s telemetry (<ids>)…**. Opening it
draws
the card in the row: what will be true afterwards, the device it touches and the undo first;
each subscription ticked, with its receiver line from intent; the exact program one level down;
a reason; and the button, named for the work, **Re-subscribe <device>'s telemetry (<ids>)**,
busy on itself until the card answers in place. It is offered only for a device found in
exactly one network.

**While a run holds the device**, nothing here offers a second one. The row's action, on its
line and under What to do, reads "<run> running since <time>, by <who>" with **Open the run**,
which opens the device's page on that run's card. The card opened while a re-subscribe of the
device is going (a refresh, a second tab, another person) draws that run, never the offer
again; held by any other operation, it draws the program and, in the button's place, "Not
offered while <device> is held: <run> running since <time>, by <who>. One operation per device
at a time." The action and the button return by themselves when the run ends. The server
refuses a second operation on a held device whatever a page drew: the page reads the same hold.

Above the card, the opened row says what Mercury's own records hold about the loss, with no
AI ([A lost telemetry stream, opened](needs-attention#a-lost-telemetry-stream)): how long the
device has sent nothing; **Seen before on <device>**, when a past loss on it matches, with how
that one ended and how long it held (a re-subscribe that read the stream back is named as the
operation that fixed it, with its record); whether it needs you; and **Mercury's diagnosis**
of this loss with when it was read, or that none is recorded, that one was not made, or that
its record could not be read. They are what you read before you decide to re-subscribe.

The program and the button are always for the subscriptions ticked: ticking or unticking one
draws the card again for that selection. A subscription of the device that is not in the alert
and sends to the same receiver (the same address and port) as one that is, is listed too,
unticked. While it is unticked the card says so: it may keep the old connection open, so the
ticked one may rejoin that connection instead of dialling again. Tick it to re-subscribe them
together.

## Who can confirm it

A verified person: someone signed in through the access proxy, or with the installation's
local account where Mercury listens on this machine only. The record names who confirmed and
how they were verified, and History shows both. A request from nobody, or from a service, is
refused first, before its subscriptions, hashes or reason are judged, saying who it was taken
to be; nothing is sent.

## The program

For one subscription, two sends with 10 s between them, the receiver line exactly as
committed intent holds it:

```
configure terminal
telemetry ietf subscription <id>
 no receiver ip address <address> <port> protocol <protocol>
end
(wait 10 s)
configure terminal
telemetry ietf subscription <id>
 receiver ip address <address> <port> protocol <protocol>
end
```

For several, a batch: every ticked receiver removed first, in the order the card lists them,
each its own send; then one wait of 10 s; then each added back, in the same order. For 101 and
102:

```
configure terminal
telemetry ietf subscription 101
 no receiver ip address <address> <port> protocol <protocol>
end
configure terminal
telemetry ietf subscription 102
 no receiver ip address <address> <port> protocol <protocol>
end
(wait 10 s)
configure terminal
telemetry ietf subscription 101
 receiver ip address <address> <port> protocol <protocol>
end
configure terminal
telemetry ietf subscription 102
 receiver ip address <address> <port> protocol <protocol>
end
```

Removed and added back one at a time, the subscription put back would find the other still
holding the stale connection and rejoin it. With every ticked receiver removed first, no ticked
subscription refers to that connection during the wait. No ticked subscription sends anything
from its removal until its re-add.

Each subscription has its own hash, and the selection has one too, over the whole program in
its order: the card carries both, and a confirm for another selection than the one drawn is
refused, naming both selections and both hashes.

An IPv6 receiver (`receiver ip address 2001:db8::10 57000 …`) is sent the same way. Removing a
receiver is a removal, so it is Mode B: you choose each subscription, your reason is in the hash
and the record, and the removal is allowed only where it was measured (IOS-XE: the operator's
hand run on a lab router, 2026-11-08). A platform where it is not measured is refused, naming
why.

## The steps

1. `plan`: each chosen subscription's receiver is read from the device's committed intent. A
   subscription intent does not declare, one with no receiver, or a platform where removing a
   receiver is not measured is refused, naming why, before anything is read or sent.
2. `hash`: the confirm must be a verified person's (above). Each subscription's program is
   recomputed and compared with the hash the card showed, and the whole program, in its
   order, with the selection's. One that moved is refused, naming both hashes (and, for the
   selection, both sets of subscriptions); nothing is sent. Your reason must be the shape of a
   reason.
3. `hold`: the device is held for the whole operation, one operation per device; another
   operation holding it refuses this one, by name.
4. `started`: the run is recorded before anything is sent, saying it changes configuration, so
   self-healing reads the device's own configuration lines during it as Mercury's, never as a
   change from outside.
5. `before`: each receiver's state and connection (through the reads engine, on History ›
   Reads), the collector's sessions from the device, and the running configuration.
6. `remove`: each ticked receiver is removed, one send each, in the card's order. After each,
   the configuration is read back, and it must differ from before by exactly the receiver
   lines removed so far. A removal that changed nothing, took more than its line, or could
   not be read back stops the removals there: the subscriptions after it are never touched,
   and say so.
7. `wait`: 10 s, once, after the last removal.
8. `re-add`: each receiver that was removed is added back, one send each, and read back. One
   that did not land is sent once more; the others are still added. The running configuration
   must then read as before, line for line (or differ only by a receiver that did not come
   back, which is said).
9. `verify`: for each subscription whose receiver is back, for up to 290 s (2.5 times the
   116 s measured from a re-add to the stream's data), three checks, each passed, failed or
   "can't tell" (a read that could not be made decides nothing, and says why):
   - **the device:** its receiver reads Connected on a connection that is not the one that
     subscription read before the run. Connected alone is not proof: a stuck device reads
     Connected too, and "the same connection as before" fails;
   - **the stream:** the subscription's series is in Prometheus, by the lost-stream alert's own
     query;
   - **the collector:** a new session from the device on the stream's port, receiving data.
     A session that was there before and still stands, receiving nothing, is flagged
     **stale half-open**: a flag, not a failure.
10. `rollback`: when the removals stop part-way, every receiver already removed is still added
    back. A receiver that did not come back after the re-add and its one retry is the danger
    state "<device>'s receiver for <id> is removed", in the result and the record, and the
    card offers Re-add the receiver for each one. A run that breaks part-way takes every
    receiver whose removal it sent and whose re-add it did not read back as removed, and says
    so the same way.
11. `record`: the run is written with who, when, why, the hash, each send and each check, and
    each subscription's own outcome. History shows it.

## What it ends with

Each subscription has its own outcome, and the run's is its worst one, never green over a
partial:

- **Re-subscribed; the stream is back**: all three checks passed, for every ticked
  subscription.
- **Re-subscribed; whether the stream is back could not be told**: a check could not be read.
- **Re-subscribed; the stream did not come back**: the configuration is at intent, and a check
  failed within 290 s. Never green: diagnose the stream again.
- **The receiver is removed**: its re-add did not land. Re-add it (below).
- **Stopped part-way; not every chosen subscription was re-subscribed**: a removal failed after
  others had been removed. Those were added back and checked; the one that failed, and any
  after it ("nothing was sent for it"), are as they were.
- **The receiver was not removed; nothing changed**, or **the configuration is not as before**:
  each says what the read-back showed.

**Where the outcome is read.** A run that ended always leaves its outcome in three places, so
it is never lost by leaving the page, refreshing it, or Mercury restarting:

- **On the card**, in place: the outcome first, each subscription's three checks, then **The
  steps taken**: the steps above on one stepper, each done, failed, not reached or not needed,
  the failed step first with what it read (each verify with its own device, stream and collector
  checks), and every step as it was recorded with its time. A run that did not end clean offers
  the next action under it: **Re-add the receiver for <id>…** when it left one removed, else
  **Preview a re-subscribe again…**; both draw the card again and send nothing.
- **On the lost stream's row**: the card opened again within a day leads with **The last
  run**, who ran it, how it ended and the steps it took, above the offer to run it again.
- **In the top bar's In progress chip**: one row while it runs, **Re-subscribe telemetry** on
  its device, and when it ends an entry under **Finished, not opened yet** for the person who
  started it, with its outcome and how many steps it recorded, until they open it. **Open the
  result** opens the device's page on the run's card. The entry is read from the run's record,
  so it is still there after Mercury restarts, for a day after the run started.

## Re-add the receiver {#re-add-the-receiver}

When a run left a receiver removed, the card leads with it, in danger, and offers **Re-add the
receiver for <id>**, one for each receiver still out: the re-add alone, through the same plan,
hash and hold, then the same verify. Adding a receiver removes nothing, so no reason is needed.
A receiver stays listed until a run adds it back: a later run of another subscription, or one
that was refused, does not hide it.

1. `plan`: the receiver from committed intent.
2. `hash`: the program recomputed and compared with the one the card showed.
3. `hold`: the device held.
4. `started`: recorded before anything is sent.
5. `before`: the receiver's state and the collector's sessions.
6. `re-add`: the receiver added back, once more if it did not land.
7. `verify`: the three checks, as above.
8. `record`: the outcome, on History.
