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
4. `analyse`: when the network's AI analysis of a can't-fix is on (a background AI feature,
   off by default, turned on in Settings › AI), it starts it. Where the network's device state
   class is also on, the analysis may ask Mercury for up to 3 read-only reads: Mercury checks
   each against the AI read set, runs the ones it allows as the device's read-only account,
   logs each answer's size and hash before anything is sent, and asks a second call with the
   answers, masked. Each read is a row on History beside the two calls, and the incident's step
   log says what was asked, refused and run. With the class off, the analysis is one call and
   asks for no read.
5. `wait`: it waits for the analysis for up to 60 seconds, never longer, so a slow model never
   holds the notice.
6. `send`: it sends Mercury's facts first (what was detected, Mercury's diagnosis by each
   hypothesis's rule, the ends it read and its strength, then the steps tried and their
   results), then the analysis, or its state (pending, not run, couldn't analyse), then the link
   to the incident, to every destination of the network's team that is verified and on. A
   diagnosis not finished in time is said so, and follows as its own event.
7. `follow_up`: when a pending analysis arrives, it is sent on the same thread.

Nothing in self-healing reads the analysis or the notice: they are for a person.

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
