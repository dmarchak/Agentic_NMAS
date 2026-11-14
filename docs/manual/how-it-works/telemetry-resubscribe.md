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

**While a run holds the device**, nothing here offers a second one. A second line under the
row's title reads "<run> running since <time>, by <who>", and the right side of the line, and
What to do, hold **Open the run** alone, which opens the device's page on that run's card. The
card opened while a re-subscribe of the
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
5. `before`: each receiver's state and connection (through the reads engine, as the run's own
   read), the collector's sessions from the device, and the running configuration.
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

   The three are read again every 10 s until each passes or the 290 s end. Every read goes
   into the run's record under this step as it is made: when, what was asked, whether it
   passed, was read and did not, or could not be read, and what it found. The record is
   written after each round, so a run still going shows the reads made so far.
10. `rollback`: when the removals stop part-way, every receiver already removed is still added
    back. A receiver that did not come back after the re-add and its one retry is the danger
    state "<device>'s receiver for <id> is removed", in the result and the record, and the
    card offers Re-add the receiver for each one. A run that breaks part-way takes every
    receiver whose removal it sent and whose re-add it did not read back as removed, and says
    so the same way.
11. `record`: the run is written with who, when, why, the hash, each send and each check, and
    each subscription's own outcome. History shows it.

**While it runs**, the card draws the run on one stepper of five stages, from the steps the run
itself has recorded: **Planned** (read intent, check hashes, hold the device, record the start,
read before), **Removing** (each removal, and the wait after the last), **Re-adding**,
**Checking** (each verify) and **Done** (the record); a Re-add the receiver removes nothing, so
it has four. Each stage is one plain sentence ("Removing 101's receiver…", "Waiting after the
removal", "Checking 101's stream is back"), its time and its state (**done**, **in progress**,
**not started**, **failed**, **not fully done** or **not reached**), and nothing is drawn done
that the run has not recorded. Open a stage to read its steps, one line each in two to four
words ("Read intent", "Hold <device>", "Remove 101", "Wait 10 s", "Re-add", "Verify 101",
"Record"), the full words, as listed above, on hover. At the wait the stage counts down ("6 s
left of 10 s") from when the wait began and the 10 s the run declared, and when the time is up
it says so and waits for the run's next step. At each verify it counts down the longest the
verify waits ("up to 290 s: 212 s left"); the verify ends sooner when all three checks pass. The card moves by itself at
each step, and at each round of a verify's reads. In the top bar's **In progress**
list the run is one row, **Re-subscribe telemetry**, whose words are the step it is in ("Wait
10 s · step 7 of 11"), never "starting" or "started". A step that reads draws, while it runs,
the newest read of each check and one line saying how many reads it has made.

**A run that stopped.** If the run's record says it is running, and nothing is running it (this
server holds no job for it, and no re-subscribe holds the device: a hold ends when its process
does), the card says so in place of "Re-subscribing…": "This run stopped before it recorded an
outcome: no step recorded since <time>", with the steps it had recorded, those it never reached
marked **not reached**. Whether each receiver is in place is then not known from the record:
read the device's configuration first. **Open the card again…** draws the card afresh, a read
that sends nothing: it leads with Re-add the receiver for each receiver the run removed and did
not put back.

## Where the run's reads are kept {#reads}

The run reads the device many times: once for each subscription before, then every 10 s in the
verify. Each of those reads belongs to the run. It goes through the reads engine, so it is
checked against the command policy, masked and kept as any read is, and it is kept naming this
run and the step that asked. It is recorded as the re-subscribe's own read, for you: the run's
record names you as the person who ran it, and each read names the run.

None of them is a Show commands row on History, and none is in Show commands' recent runs or
in the device's recent reads on Ask the device. They are in the run's one record, under `before` and
`verify`, in order. History's row of the run says them in a line for each step ("26 reads,
about 13 s apart: 1 pass, 25 fail; the last: ..."). The reads of Prometheus and of the
collector's sessions are listed the same way; they are not device reads, so they name no
stored answer. [How Show commands works](show-commands#an-operations-reads) has the rule and
what History does with reads kept before it.

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

- **On the card**, in place: the outcome first, in a box that says what failed and why, once;
  each subscription's own line; then its stages, the one that failed naming the step it
  stopped at ("Verify 101 failed"; why is the box's), and Done never green over a failure; each
  stage opens to its steps, one line each with its state, its time and its one-line outcome.
  What a step that did not pass read sits under that step alone, closed, as
  **What it read** (each failed verify's device, stream and collector checks, one line saying
  its reads, and every read one level further down, **The N reads**); a step that passed
  shows no checks. A run that did not end clean offers the next action under it: **Re-add the
  receiver for <id>…** when it left one removed, else **Preview a re-subscribe again…**; both
  draw the card again and send nothing.
- **On the lost stream's row**: the card opened again within a day leads with one closed
  line, **The last run, <how long ago>: <how it ended> · N steps · Show**, in the outcome's
  colour; opened, it shows who ran it and the steps it took. The full detail stays on the
  run's own result card. The offer to run it again is under the line.
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

## Closing the collector's session {#collector-close}

A stream can stay lost because the collector on Mercury's host still holds the old session:
established, receiving nothing, while the device's own side reads "Disconnecting". The device
cannot dial again until the collector's side is closed. Closing another program's session is
the kernel's own operation (`ss -K`) and needs root, and Mercury runs as an ordinary account.
So the close is one small root-owned helper, `mercury-collector-close`, which Mercury may run
through one sudoers line, with no argument, and which closes nothing but one session from a
listed device to the collector's own listener.

**What uses it.** One operation, the re-subscribe above with the collector step on (below), its
button **Close the collector's stale session for <device>, then re-subscribe (<ids>)**. Nothing
else closes a session, and a stale half-open session found by the plain re-subscribe's verify
is still only flagged.

### The collector step {#the-collector-step}

![Close the collector's stale session, then re-subscribe: the plan reads the collector's sessions on Mercury's host and the close helper's dry run names the one session it would close, closing nothing; you confirm by the selection's hash, which holds that session's two ends; holding the device, the run reads before, the helper closes the session and reads it back gone, its answer kept as the receipt; a close that did not happen stops the run with nothing sent to the device; the device's connections are read until the one that read Disconnecting is gone; then each receiver is removed and added back and the stream verified, and the run is recorded.](diagrams/telemetry-collector-close.svg)

**When it is the fix.** Mercury's diagnosis of a lost stream names it when it has measured both
ends of a half-open session: the device's own telemetry connection to the collector reads
**Disconnecting** (`show telemetry internal connection`, IOS-XE's form), while the collector on
Mercury's host still holds an established session from that device with nothing received inside
the stream's 90 s window. Either end not read decides nothing, and says why. AI troubleshooting
may propose it too, from the same catalog entry; either way you approve it.

**Opening it.** The lost stream's card opens with the step from the incident's proposal, or by
**Close the collector's stale session first…** on the card, a read that closes nothing. The
card draws the session the step would close, both ends and ports, as the close helper's dry run
names it, and how long it has received nothing, above the exact program. It is not offered, and
says why, when the collector holds no established session from the device (Re-subscribe alone
is the fix), a session that is receiving data (never closed), a session whose last receive was
not read, more than one idle session, or an IPv6 collector (the helper serves IPv4 only).

**The confirm** is bound to the selection's hash, which holds the session's two ends with the
program. If the device dialled again on another port before you confirm, the session is
another, and the confirm is refused, naming the session you confirmed and the one standing now;
nothing is closed or sent.

**The steps it adds**, between `before` and `remove` (the others are the re-subscribe's, above):

- `before` also reads the device's telemetry connections, so the run knows which one is to go.
- `close`: holding the device, Mercury asks the close helper to close that one session. The
  helper finds it again, closes it and reads it back gone (its answers are below). Its code,
  exit code and words are the run's receipt, on the step and in the record. Anything but
  `closed` stops the run there: nothing is sent to the device, and the outcome says "the
  collector's session was not closed".
- `gone`: the device's connections are read every 5 s until the one that read Disconnecting is
  gone, for at most 60 s. That bound is reasoned, not measured yet: the first run's time is kept
  in its record, and the bound becomes 2.5 times it. Still there at the end, it is said, and the
  re-subscribe follows: removing the receivers is what released it by hand.

**Undo.** The closed session cannot be put back, and needs no putting back: the device dials a
new one, which the verify reads as the collector's new session. The receivers are put back as
the re-subscribe puts them back.

### Who installs it

A person, once, on Mercury's host, as their own account with sudo, from this release. Two
commands. The first is run as the account Mercury runs as, and writes the list of devices
whose sessions may be closed:

`scripts/nmas-collector-peers <listener address>:<port> > <peers file>`

`<listener address>:<port>` is the address and port the collector listens on, as the devices'
receivers name it. The command reads every network's committed intent and prints one address a
line: for each device whose telemetry is sent to that listener, the `source-address` its
subscription declares, or else each IPv4 address of its interfaces. What it leaves out it
says, per device. The second command installs:

`bash <release>/scripts/host-steps/c3078-collector-close-install.sh <service user> <listener address>:<port> <peers file>`

`<service user>` is the account Mercury runs as. The step:

- **Checks first, and changes nothing until every check passes**, each failed check saying
  what it wanted and what it got: the release holds the helper; `ss` is root's program and can
  close a session; the kernel allows it, where its configuration can be read (said when it
  cannot); the account exists; the collector listens on that address and port on an IPv4
  socket; every line of the peers file is an IPv4 address, and there is at least one; what is
  already installed is as this step leaves it; the sudoers file is absent or holds exactly the
  one line, and `visudo -c` accepts every sudoers file.
- **Then installs three files**: the helper at `/usr/local/sbin/mercury-collector-close`
  (root's, mode 0755); its configuration at `/etc/mercury/collector-close.conf` (root's, mode
  0644), which names the listener, the peers, the account and the path of `ss`; and
  `/etc/sudoers.d/mercury-collector-close` (mode 0440), one line, checked by `visudo` before it
  is put in place: `<service user> ALL=(root) NOPASSWD: /usr/local/sbin/mercury-collector-close ""`.
  It also makes `/var/lib/mercury-collector-close` (root's, where the helper writes its
  outcome) and its `request` folder (the account's, where Mercury writes a request).
- **Then proves the copy** with two dry runs as that account: one for a listed device, which
  the helper answers `no_match` or `would_close`, and one for an address that is not listed,
  which it refuses. Each answer is printed.
- **Restarts nothing and closes nothing.**

Mercury cannot change the list of peers: only this step, run by a person, writes it. After a
device's telemetry is added, removed or moved to another address, run both commands again;
until then the helper refuses that device's address.

### What the helper refuses

Mercury's request is one file with four values: a run id, the device's address, the device's
port, and whether it is a dry run. The helper takes nothing else from it. It refuses, saying
what it compared and both values:

- any argument on its command line;
- a configuration that is not root's, mode 0644, in a folder only root can write, or that
  holds anything but the keys it knows;
- a request that is a symbolic link (it is never followed), that is not a regular file, that
  another account owns, that is larger than 1024 bytes, that was written more than 120 s
  ago, or that is dated more than 5 s ahead of the clock;
- an address that is not an IPv4 address written plainly (four numbers, no leading zero,
  nothing around it), or that is not in the configuration's list;
- a port that is not digits from 1 to 65535;
- a request that names a listener: the listener is the configuration's alone;
- anything but exactly one established session from that address and port to the listener.
  None is "it may have closed already"; two or more are refused by their count; and a
  session of any other listener or device in `ss`'s answer refuses the whole run.

An IPv6 device address, an IPv6 listener, and a session held by an IPv6 socket (a collector
listening on every address of both families holds its IPv4 sessions that way) are not served
yet. Each is refused saying so, never as "no session".

When it does close, it runs `ss -K` once, naming all four ends of the session, and then reads
the sessions again: the session gone is the success, and a session still listed 2 s later is
a failure that says so. Every run, refused or not, is one line in the host's journal under
`mercury-collector-close`, and the same line is the outcome Mercury reads.

### Its answers

Each answer has a short code and an exit code:

- 0: `closed`, or `would_close` for a dry run that found exactly the one session;
- 20: `no_request`; 21: `refused_symlink`; 22: `refused_owner`; 23: `refused_file`; 24:
  `refused_size`; 25: `refused_stale`;
- 30: `refused_shape`; 31: `refused_id`; 32: `refused_peer`; 33: `refused_ipv6`; 34:
  `refused_port`; 35: `refused_listener`;
- 40: `no_match`; 41: `many_matches`; 42: `filter_not_held`; 43: `ss_unread`; 44:
  `ss_failed`;
- 50: `not_gone` (the close ran and the session is still there); 51: `close_unread` (the
  close ran and the sessions could not be read again);
- 64: `refused_argument`; 70: `error`; 75: `busy` (another run is in progress); 77:
  `not_root`; 78: `config_refused`.

It never exits 1: that is sudo's own refusal, which Mercury reports as the helper not being
installed for its account, with the install step to run.

### The dry run

`scripts/nmas-collector-close-dry-run <device address> <device port>`

Run as the account Mercury runs as. It asks the helper what it would do for that session and
prints the answer: `would_close` when exactly that one session is there, or the refusal a
real request would get. A dry run makes every check and the read of the sessions, and never
runs `ss -K`. This command has no option that closes.

### The undo

`sudo rm /usr/local/sbin/mercury-collector-close /etc/mercury/collector-close.conf /etc/sudoers.d/mercury-collector-close`

With the three files gone nothing can run the helper. `/var/lib/mercury-collector-close`
holds only the last outcome.
