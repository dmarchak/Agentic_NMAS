# Notifications: how a team is told

Mercury tells a network's team when self-healing needs a person or did something they should
know: a can't-fix, a fix waiting for a person, a network halted or a device held, every automatic
heal, and an incident cleared. Who is told, and about which events, is chosen on each network's
**Self-healing** tab (**Who is told**); the teams, their addresses and webhooks and the email
relay are on Settings › Installation › **Notifications** ([Notifications](settings#notifications)).
A message carries Mercury's facts and a link, never a configuration line or a secret.

![A notification of a can't-fix: the notifier finds each new can't-fix recorded in the last ten minutes and not yet told, and takes it once under the store's lock; if the network's AI analysis is on it starts it as a background call and waits for it at most 60 seconds; it then sends Mercury's facts, the analysis or its state (pending, not run, couldn't analyse), and the link, to the network's team: an email through the relay and each webhook, signed; each attempt is a row in the delivery log, a failure tried three times and then raised under Needs attention; a pending analysis that arrives later is sent on the same thread. Nothing reaches a device.](diagrams/notifications.svg)

## A can't-fix, told {#cant-fix}

After each pass of self-healing's runner, the notifier tells each new can't-fix once:

1. `due`: it finds each can't-fix recorded in the last 10 minutes and not yet told.
2. `claim`: it takes it once, under the store's lock, so it is told and analysed once, however
   many of Mercury's processes look.
3. `diagnose`: for an Alert incident, it runs Mercury's own diagnosis first, read-only, and
   waits for it up to 150 seconds, so the analysis and the message both carry it. A Never
   incident is told with none.
4. `cleared`: when that diagnosis reads the symptom gone (the adjacency up at both ends, or
   every probe answered), it waits until nothing has been logged about it for the flap window
   (10 minutes by default) since it was last seen. Still gone, read again from the readers'
   stored values, with nothing new in that time, the incident ends "cleared by itself at HH:MM
   UTC, nothing to do": no message is sent and no analysis is asked. Seen again in that time,
   or not read gone, it is told as below. An incident that ended nothing to heal by the time it
   would be told is not told either.
5. `analyse`: when the network's AI analysis of a can't-fix is on (a background AI feature,
   off by default, turned on in Settings › AI), it starts it. Where the network's device state
   class is also on, the analysis may ask Mercury for up to 3 read-only reads: Mercury checks
   each against the AI read set, runs the ones it allows as the device's read-only account,
   logs each answer's size and hash before anything is sent, and asks a second call with the
   answers, masked. Each read is a row on History beside the two calls, and the incident's step
   log says what was asked, refused and run. With the class off, the analysis is one call and
   asks for no read.
6. `wait`: it waits for the analysis for up to 60 seconds, never longer, so a slow model never
   holds the notice.
7. `send`: it sends Mercury's facts first (what was detected, Mercury's diagnosis by each
   hypothesis's rule, the ends it read and its strength, then the steps tried and their
   results), then the analysis, or its state (pending, not run, couldn't analyse), then the link
   to the incident, to every destination of the network's team that is verified and on. A
   diagnosis not finished in time is said so, and follows as its own event.
8. `follow_up`: when a pending analysis arrives, it is sent on the same thread.

The email's subject is "[Mercury] <device> on <network>: could not fix". Its text says, in
order: what happened, the outcome, what was detected and when, the fix kind, Mercury's
diagnosis, then **What Mercury tried**: every step the incident's record holds, in order, one
line each, as the device page's stepper says it: the time it was recorded, the step's short
label ("Read edge-b", "Decide"), what it recorded, and its result in words ("done", "failed",
"not fully done"). Then what to do, the AI analysis or its state, **Open in Mercury**, the
incident's own page (`/v2/incident/<id>` on its network, [An incident's page](incident)),
which draws the incident's stages from its step log after any restart, and the incident's id
with when it was sent. One function builds that address, so a can't-fix's email, an action's
end and their webhooks all link the same page.
Every time is in the time zone of the host Mercury runs on, named once on the last line ("Times
are in …"); a time on the other side of a daylight-saving change says its own zone beside it.
People are named by their display name, never by their sign-in identity; in what the analysis
is sent of the steps tried, each person is a stable label ("person-3f9a1c"), never their
identity or name. With the address Mercury is reached by not set
(Settings › Installation › Notifications, the Email relay card), the link is the page's path
alone, and the email says why.

A can't-fix is told once per incident: an incident still standing on its decision and judged
again later ([Standing](heal#standing)) is never told a second time. Nothing in self-healing
reads the analysis or the notice: they are for a person.

## An action's end, told {#actions}

Self-healing's actions (a port bounce, an OSPF adjacency reset, a BGP session clear and an
approved dampening change; [Self-healing](heal#actions)) each end in their own job, often minutes
after the can't-fix that led to them was told. Each end is told once, on that incident's thread,
so it arrives under the first message:

1. `due`: the notifier finds each action that ended in the last 10 minutes and is to be told:
   every end a person must look at, and an end that worked only when it was automatic (an
   approved action that worked is the approver's, and is not told).
2. `claim`: it takes it once, under the store's lock, however many of Mercury's processes look.
3. `send`: it sends what the action acted on and how it ended ("edge1 GigabitEthernet4 bounced,
   still flapping: ... a dampening change waits for a person"), the decision that chose it, its
   steps and their results, as the stepper says them, and **What to do** in the words of its
   Needs attention item, then the link to the incident's page, the same page a can't-fix links.
   The program's lines are withheld, as a can't-fix's are.

Which event it is sent as decides which teams are told, by their choices under **Who is told**:

- **can't fix**: a bounce still flapping, its adjacency not formed, not verified, or nothing
  sent; a clear whose session did not come back, not verified, refused by the device, or
  nothing sent; an approved dampening rolled back, not verified, or nothing sent;
- **halted or held**: a bounce reverted by its timer, repaired or NOT RESTORED; a soft clear
  that reset its session; an approved dampening NOT RESTORED (each halts the network);
- **every automatic heal**: an automatic bounce that ended bounced and stable, or an automatic
  clear that ended cleared, sent as "an action taken, verified".

## Where it goes {#destinations}

- **Email**, through the installation's relay, to each verified address of the team. With no
  relay host set, no email is sent, and the card says so.
- **Webhooks**, each a receiver's URL: the generic format is JSON with an HMAC-SHA256 signature
  over its timestamp and body, so the receiver can check it came from Mercury.

Each destination is verified before it receives anything: an address or a webhook is added off
and sent a code, which a person reads where it arrived and types back on its team. **Test send**
sends one message now.

## The delivery log {#log}

Every attempt is a row in [History](history), kind notification: its channel, its recipient
masked to its domain (a webhook to its host), its outcome and its error. A failed delivery is
tried three times, and then raised under **Needs attention** with its error, until the next
delivery to that destination succeeds or a person acknowledges it. A notice that was not
delivered is never shown as sent.
