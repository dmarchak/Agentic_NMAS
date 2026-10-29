# The installation's settings: save, test, replace a token, turn NetBox writes off

The installation's own settings apply to every network, standalone ones included: the central
NetBox, Proxmox, the author line of Mercury's commits and this host's address. They are on
**Settings › Installation**: the **NetBox connection**, **Proxmox**, **Commit author** and
**Server** cards on the Connections tab (beside the records database, which has its own page).
Its other tabs are Access and identity, Platforms and roles, and Diagnostics. Nothing here
contacts a device.

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
   date is `YYYY-MM-DD` or empty; the port is a number from 1 to 65535; the bind address is
   letters, digits and `. : _ -`; an email is `name@domain`; the commit author's name is one
   line, not empty; the AI card's cap per day is an amount in US dollars more than $0, with
   no maximum (see [The day cap](#ai-cap)). A refusal names the field and what it accepts,
   and nothing is saved.
2. `write`: only the fields you changed are written, to the installation's settings, for
   every network. Read: the settings as they stand, compared with what the card showed when
   you opened it. Sent: nothing. Recorded: the values. A field you left as it was is not
   written, so a change another person made to it since stands. A field you changed that
   another person also changed since is refused, naming what it was when you opened the card
   and what it is now, and nothing is saved: the card is drawn again with the values now.
   Saving what is already stored writes nothing and says "Nothing changed".
3. `record`: the save is appended to the installation's settings record, a file. Read:
   nothing. Sent: nothing. Recorded: who, how that was established, when, the card, and each
   field written with its old and new value (a card's fields are never secrets: a token is
   changed by **Replace…**, which records only its name; a value is masked as it is kept
   all the same). **History** draws each save under the kind **Installation settings**, for
   example "AI (hosted): Cap per day $50 → $80", with who and when. If the record could not
   be written the card says so; the save is made either way.

The **Server** card's bind address and port are read when Mercury starts: its Save says the
change waits for the next restart, and Mercury listens where it did until then. The TFTP root
is not on this card: it was read only by today's device file pages, and it left with them
when they were removed (Mercury's own transfers serve their files from memory).

## Test {#test}

**Test** asks the service with the settings as saved (save first: it tests what is stored, not
what is typed), and changes nothing. NetBox is asked for its status in the card's auth scheme,
then for one row of each kind of object Mercury reads: a token missing permission to view one
fails the Test, naming each kind, and a refused token is drawn with NetBox's own reason and
what to do about it. Proxmox is asked for its version with the token. The answer is drawn in the card: the
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

## AI (hosted) {#ai}

The **AI (hosted)** card, first on Settings › Installation's **AI** tab (it moved there from
Connections, which keeps one line linking to it), holds what Mercury's AI features need to
reach a hosted model: the
**API key** (a secret, typed by a person with **Replace…**, never drawn back), the **Cap per
day** in US dollars for the installation, and whether **hosted AI** is allowed. Its table,
read-only, names each task's pinned model (its exact id), the prices its cap uses (input and
output, cache write and read, US dollars per million tokens, from Anthropic's pricing page,
with the date they were read; the card says so when they are older than 90 days), and each
task's **cap per call**: its model's worst case at the task's prompt and answer bounds. A task's
model never changes at run time; changing it re-runs that task's recorded cases. A Haiku task's
prompt is held under 100,000 tokens, since over it every rate is five times; a longer one is
refused, saying so. It is off
until a person allows it. Every call goes through one gateway, which masks what leaves the
host, refuses a call over a cap before sending it, and records it under **History › AI calls**
(the feature, the model, the verdict, the cost, who asked). Every call also names what
started it, recorded with it: a person's press (the person the request verified), an
evaluation run, or a background job acting on something {{product}} found; a call that names
none is refused before anything is read or sent. No background feature runs today: each will
be off for every network until an admin turns it on. **Spent today** is the day's total
from that record; a record that cannot be read refuses every call. The day begins at midnight
in the zone **The day begins at** names, beside the cap: UTC unless set, or a time zone's name
such as America/Denver, its daylight-saving changes followed. **Spent today** says when the
count starts again, "resets 18:00 MDT (00:00 UTC)": your own time first, from your browser,
and UTC's beside it. It is the same instant the gateway counts by. The card's **Test**
is one small, real call: the model is given a word Mercury chose and must give it back, so a
passing Test means the allowance, the key, the mask, the caps, the model and the record all
held. It costs a fraction of a cent and is recorded like any call.

## The day cap {#ai-cap}

The **Cap per day** is the most the installation's AI calls may spend in a day, in US
dollars. Before each call the gateway adds today's spend, what the calls still in flight have
reserved, and the call's worst case, and refuses the call, sending nothing, when the sum is
over the cap; the refusal names each amount and the cap. A call's worst case is its prompt as
the provider counts it (Anthropic's own token count, asked before the call; when the count
cannot be had, a deliberately high estimate from the request's size, and the call's row says
which), every prompt token priced as a cache write, plus the most the answer may be.

**Calls at once never pass the cap together.** Each call's worst case is reserved against
the cap, under one lock every worker shares, before it is sent, and released to what the call
actually cost once it is recorded. A second call made while the first is in flight is judged
with the first's worst case counted. A reservation left by a worker that stopped mid-call is
released after about ten minutes (2.5 times the longest one call can take). If the
reservations cannot be read, every call is refused, saying so, until they can or until no
call they could hold is still in flight.

**A call the record could not take still counts.** If the record of AI calls refuses a sent
call's row (its disk or database refusing writes), the call's reservation is kept, never
released by time, holding what the call cost (its worst case when that is unknown), and
**Needs attention** names the call: it is missing from History until the record takes it.
Mercury asks the record to take the row again before every AI call; when it does, the row
appears in History at the call's own time, the reservation goes and the Needs attention row
clears. Until then the call is counted against the cap as a call in flight, on every day,
never left out.

The provider bills what is spent, to the account the API key belongs to; the cap is
Mercury's own limit, set below the provider's.

The cap is yours to set: **{{product}} has no ceiling of its own**, so a deployment that
spends more than a laboratory does sets what it needs. A cap is an amount more than $0;
$0 and a negative amount are refused, saying so. To stop AI calls, turn hosted AI off
instead.

**A large increase asks first.** A new cap at least double the old one, or at least $50 more,
is not saved at once: the card shows what it means, "Up to $80 a day, about $2,400 a month
at full use" (a month counted as 30 days), with **Save** and **Cancel**. Nothing is written
until that Save, and one more press saves it. The confirmation keeps what the card showed
when you opened it, so a change another person made to the cap meanwhile is still refused,
naming both values. A smaller change, or a decrease, saves at once.

**No cap** is a choice of its own beside the field, never an empty field. Ticking it and
pressing Save shows a stronger confirmation: Mercury would not stop AI spend, and the
provider's own limit is the backstop. Type `no cap`, give your reason (one line, up to 300
characters), and press **Save with no cap** to set it. Without the words or without a reason
the press is refused in place, naming what is missing, and nothing is written; a reason you
gave is kept in the field for the next press. The reason is kept in the installation's
settings record beside who, when and the change, and History draws it (the row's **Reason**).
While no cap is set the card says "No cap is set: Mercury does not stop AI spend; the
provider's own limit is the backstop", followed by who chose it, when and their reason;
**Needs attention** shows a warning, "AI spend uncapped", for as long as hosted AI is on
(see [Needs attention](needs-attention)); the gateway refuses no call for the day's spend (a task's cap per call still applies, and
its refusal says no day cap is set), and the toolbar's spend chip, once built, shows "no
cap" for as long as it is set. To set a cap again, untick No cap, give an amount and Save.

Every change to the cap, like every Save on these cards, is recorded with who, when, and its
old and new value, and is drawn on **History** (the kind **Installation settings**): "AI
(hosted): Cap per day $50 → $80".

## The AI mark, and a control shown disabled {#ai-mark}

Every control that needs AI carries the same small **AI** mark: **Ask in words** on History ›
Query, **Explain** in an alert's evidence pack, and this card's **Test**. Hover it to see the
task it runs, the model that task is pinned to, and the most one call of it may cost (its cap
per call, from the table above).

Before drawing such a control, {{product}} asks what the gateway would ask before sending
anything, in the same order: is hosted AI allowed, is a key stored (only whether one is; its
value is never read to draw a page), and would today's spend plus this task's cap per call
still be within the cap per day. If any answer is no, the control is still drawn, never
hidden, but disabled, its box not fillable, and the reason is written under it:

- **hosted AI is off**: allow it on this card, with a reason;
- **no Anthropic API key is set**: a person types it with **Replace…** on this card;
- **today's AI spend plus this task's cap per call is over the day cap**: both amounts and the
  cap are named, with when the day's count resets (your time, and UTC's), or the cap per day
  can be raised here;
- **the record of AI calls cannot be read**: today's spend is unknown, so no call is made.

A person who may change settings also sees a link to this card. The path beside each control
needs no AI and stays usable whatever the state: the builder (History › Query), the evidence
pack (Monitoring › Alerts), the intent editor (a device's Intent tab), and this card's
**Save**, **Replace…** and **Allow**. The state is the one when the page was drawn: if hosted
AI is turned off in another tab, or the day's cap is reached meanwhile, the gateway still
refuses the call before anything is sent, and the control says why in place.

## Allow hosted AI {#ai-allow}

Sending network data to a hosted model is a person's decision, so **Allow** needs a reason of
your own, one line of 10 to 300 characters.

1. `check`: the reason is 10 to 300 characters. Read: nothing. Sent: nothing. A refusal
   changes nothing and hosted AI stays off.
2. `write`: who, when and the reason are written as the installation's allowance. Read:
   nothing. Sent: nothing.
3. `record`: the allowance, with the reason, is appended to the installation's settings
   record.

## Turn hosted AI off {#ai-off}

1. `write`: the allowance is emptied. Already off: nothing is written and the card says so.
2. `record`: who and when are appended to the installation's settings record.

From then on every call is refused, named "hosted AI is off", until a person allows it again.

## Change the platform map {#platforms}

On the **Platforms and roles** tab: a device that comes from NetBox becomes something Mercury
can open a session to through the **platform map** (its NetBox platform → the netmiko driver, the config dialect Mercury renders
from, how it delivers and whether it supports NETCONF, with a default driver for a platform
the map lacks). What it is (router, switch or firewall) is **NetBox's**: its Device Role's
`mercury_kind` field, read with the inventory; a role without one is "not classified in
NetBox", never guessed from a hostname, and is set on the role in NetBox. Devices from a
local list keep the driver and role their list names. A driver is chosen from the drivers Mercury supports, a
dialect from the dialects it knows: neither is typed.

A change is never saved blind. **Remove**, **Add** and **Preview changes** each show what it
would do first:

1. `check`: every row is checked: a supported driver, a known dialect, ssh or netconf, a NetBox
   slug; a new slug not already in the map. Removing a platform a device uses is refused,
   naming the devices.
2. `preview`: from each NetBox network's last inventory (never a refresh, so the preview
   writes nothing), every device whose driver the change moves, network by network; devices
   skipped today for an unmapped platform that would now load. **Test** opens one read-only session
   to one of the devices with its new driver and asks `show version`, through the same reads
   as Show commands (recorded there), so a driver that cannot reach the device is seen before
   it is saved.
3. `write`: **Save** writes the map, bound to the preview: if the map or any device moved
   since, nothing is saved and the card says to preview again.
4. `record`: who, when and how many devices changed are appended to the installation's
   settings record.
5. `refresh`: each NetBox network refreshes its inventory from NetBox, so its devices take the
   new driver.

## Record a decision about access {#record}

The **Access and identity** tab is read-only by design: a session must never lower the gate it
is using, and a wrong team domain or audience locks everyone out, or lets everyone in, without
saying so. It shows each of the twelve gates (for each action, whether it needs a verified
identity and whether it needs a person), the Cloudflare Access values (to a verified person
only), the service tokens and who you are. v2 changes none of these values, by design: a
value is changed in the installation's settings file on the host.

Each value is **defaulted** (nobody decided), **recorded** (agreed, equal to the default) or
**chosen** (differs from it). **Record this decision** turns defaulted into recorded:

1. `check`: each setting named must be an access or identity setting. Read: nothing. A
   refusal names the setting, and nothing is written.
2. `write`: the value already in force is written to the settings file, so nothing changes;
   one already in the file is left as it is.
3. `record`: who, when and the names of the settings are appended to the installation's
   settings record; the gate then reads "recorded by" that person, on that day.

## Console servers: a port's record {#console-servers}

Out-of-band ZTP reaches a device's console through a console server ([Out-of-band ZTP](onboard#out-of-band-ztp)). NetBox says WHICH console-server port a device's console is cabled to; the **Console servers** tab says HOW Mercury reaches that port, one record per port, keyed by the port's NetBox id: its driver (**Command bridge**, an SSH console server whose forced command bridges one console chosen by a container name, or **Raw TCP**, a console port reached directly or through an SSH jump host), the host (an IPv4 or IPv6 address, or a hostname), the container name or the TCP port, the jump host and SSH port, and the NAME of a key in the credential store, never a key and never a command. The tab lists every record with its NetBox port (or says NetBox could not be read), the SSH host key held for it, and NetBox's console-server ports with no record yet, each with **Set up…**. A console server's own device and port are made in NetBox first.

**Save the record** (Add a port record…, Set up… or Edit…), as you:

1. `check`: every field is checked against the driver's: a field the driver does not hold (a container on a raw TCP port, say), a missing one, a host that is no address or hostname, a port outside 1 to 65535, a key name that is not a name, or a container name the console host's bridge would refuse, is refused, every one named, and nothing is written.
2. `write`: the record replaces the port's, under the store's lock, atomically and owner-only; a store that cannot be read refuses every write and is kept as it is.
3. `record`: the write is logged in the store with who and when; the tab's Changes card draws the last ten.

**Remove…** says what stays (NetBox's port and cables, and the key) and that a device whose console path ends there cannot be surveyed until a record is set again; **Remove port <id>'s record** forgets it, logged the same way. Nothing here contacts a console server or a device.

## Console servers: a key {#console-server-keys}

Each console server signs Mercury in with a dedicated key that Mercury makes, so no person handles a secret and none crosses the console. **Generate a key…** asks for the key's name, the user on the console host, and the paths of the bridge wrapper and its allowlist on that host (the host step's paths, filled in). **Generate the key**, as you:

1. `check`: the name, the user and both paths are checked before a key is made; a name that already holds a key is refused unless you tick **Replace** (the console host then refuses the old key once the new line is installed).
2. `generate`: a new ed25519 key pair is made here.
3. `store`: the private half is stored encrypted in the credential store under the name. It is shown nowhere, now or later.
4. `show`: only the public key, its fingerprint, and the exact `authorized_keys` line, `restrict,command="<wrapper> <allowlist>" ssh-ed25519 …`, which you install for that user on the console host: the key can then do one thing, run the bridge, which opens only a console on its allowlist.

Name the key as a port record's Key. A refused console server's SSH host key is re-keyed on the same tab ([Re-key](rekey#console-server)).

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
2. `write`: the schedule is written to its store (`agent_timers.json`, the file the AI agent's
   timers kept it in before they left) and the checker re-arms; a network's
   switch is written to its drift state with who and when.
3. `record`: who, when and what changed are appended to the installation's settings record.

**Check now** starts a network's check in the background (the schedule would run it anyway,
only later) and is refused while one runs, in this process or another, naming who started it;
the card redraws when the check records its result, and what it found is on Needs attention.
Each step of the run is on [Check drift](drift-check).

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
