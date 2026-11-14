# Credentials

The credentials the tool holds for each network, and the record that holds them all. On the
redesigned pages it opens on the break-glass record, the page's first part, with **Profiles**
(the network's credential profiles) as the tab beside it. Each credential's expiry is not on
these pages yet (plan 7.6).

## The break-glass record {#breakglass-record}

The record is one file holding every device's credential in a network, and the key that opens
the tool's stored secrets, sealed with a passphrase you choose. It is the way back into the
devices when the tool cannot sign in to them, and the way back to the stored secrets if the host
loses its key. It belongs to the whole network, not to one device, so it lives here. Every way
in opens it here, for the network it names:

- the result of a rotation, a retirement or an adoption (each offers the export);
- Needs attention's break-glass rows (**Export it on Credentials…**,
  **Record the drill on Credentials…**);
- the Reload card's link to the device's break-glass record;
- the sidebar's Credentials.

The card at the top answers one question: does the record you hold recover every device? It
reads one of these:

- **current:** every credential in use is in the last export;
- **not current:** it names the devices rotated since, which the record cannot recover;
- **not intact:** the last download did not arrive whole;
- **none exported:** nothing says a record exists;
- **not judged yet:** job health has no judgement of this record yet;
- **unknown:** the export log could not be read, so whether a record exists is unknown, which
  is not the same as no record.

Job health judges it every 5 minutes, comparing digests and never a value. An export made after
its last check is said as such: it held the credentials in use when it was made. The card also
gives the last export: when, by whom, how many devices, the key's fingerprint and the file's
sha256, and whether the browser confirmed the download arrived intact.

**Export the record…** opens the export on this page. How it works:
[Export the break-glass record](breakglass-export). **Check a break-glass file…** opens the
copy you keep, here, in memory, and says device by device whether it still recovers them:
[Check a break-glass file](breakglass-export#check).

**The offline drill**, below the record, is the only proof the record opens without the tool.
It shows when the last drill was done and when the next is due, every 90 days. It gives the
command to run where the file is kept, and the field for the receipt line that command prints:
[The offline drill](breakglass-export#drill). Needs attention raises a row only once a drill is
overdue.

## Where a credential comes from {#what-it-is-for}

A device's credential is found in this order, first match wins: its own override, the list's
designated credential list, a platform profile, a kind profile (its NetBox role's
`mercury_kind`), a site profile, the default profile. A platform comes before the kind because
logins differ by vendor, and a kind such as `switch` spans vendors. A NetBox device no source
covers is not dropped: it is listed with the status **No login** (its words on hover name its
platform, kind and site), nothing opens a session to it, and Needs attention raises one row per
network counting them until each resolves. v2 does not
yet draw which of these a device's credential came from: the device page's Credential check
shows its age and its rotation policy only (a gap, registered, C1360). Values are write-only:
none is ever shown back.

## Profiles {#profiles}

The **Profiles** tab lists the credential profiles, which apply to every network on this
installation. A device a NetBox inventory brings in carries no login of its own, so it is
given one in the order above; a local inventory's devices carry theirs in it and never read
a profile for it (their read-only account comes from the profiles all the same: see
[the read-only account](#read-account)). Each row says which devices it gives its login to: `platform:<slug>` every device on
that NetBox platform, `role:<kind>` every device whose NetBox role has that `mercury_kind`
(router, switch, firewall or host; never the NetBox role's own name), `site:<site>` every device
at that site, `default` every device nothing before it covers. A profile under any other name,
or `role:` with a NetBox role's name, is stored and read by nothing, and its row says so.
The password and enable secret are shown only as set or not set, and **Password last set**
says when the password was last changed.

**Add a profile…** asks what it covers (a platform, one of the kinds, each naming the NetBox
roles it covers now, a site, or every device), the platform or site where it needs one, the
username, the password and, if its devices need one, the enable secret; a new profile needs the
username and the password. **The platform or site** is chosen, never typed: the platforms in
the platform map and the sites a loaded NetBox device is at, each by NetBox's name with its
slug beside it and how many loaded devices are on it; it stays at **none** for a kind or the
default profile, and a kind or the default given a platform or site is refused, naming both. A
platform is added on Settings › Installation › Platforms and roles. A name no device can match
is refused, naming the scope
and what exists: the kinds Mercury has, the platforms in the platform map, the sites a loaded
NetBox device is at. **Edit…** keeps any field you leave empty; **Save the profile** saves the
form. **Delete…** says what the profile covered and that those devices then take their login
from the next source; one no source covers is listed with the status No login at its next
NetBox import.
**Delete <profile>** deletes it: the login is gone from the installation, kept nowhere the tool
keeps. **Cancel** closes either card with nothing changed. Each needs a verified person, and
each is recorded on History (Credential profiles): who, which profile, and the fields set,
never a value.

**Rotation policy…** on a profile's row sets how its devices' credentials are rotated on a
schedule: off, or every N days inside a preferred window of UTC hours, at most K devices a run.
It can name only some devices (a pilot), and says **why** the policy is as it is, one line
kept with it. **Set the policy** saves the form; only a verified person sets one, and History
records who, when and the policy with its reason. The row's
Rotation policy column says the policy, how many devices follow it, how many are due and the
next due date. The **Scheduled rotation** card below the table leads with how many devices are
due, says when the last run ran and what it did, and lists each device's credential age and
next due date in three collapsed groups (due now, within their policy, no policy on); a device
Mercury has never rotated says "never rotated by Mercury" and is due. Beside the due date,
**The timer rotates it** says when the timer would rotate the device, "about <time>
(estimate)", from the timer's own rules (its policy's run at most once in any 24 hours, its
preferred window, the no-change windows, its limit a run, the five-minute look), the basis on
hover; it is the time to plan a hold around ([how it is worked out](rotate#scheduled)). A no-change window is
said in the summary ("No run starts inside <window>"). When the last run stopped on a failure,
the card says **The timer is stopped**: no scheduled run starts until a later run finishes
without one, and Needs attention names the device and the stage.
**Rotate due devices now…** previews the devices it would take, and the devices left for a
later run with why. **Rotate N device(s)** confirms that list by its hash (if the due devices
change first, nothing is sent) and runs them one at a time through the device page's
rotation, each row on the run's stepper in place; it needs a verified person, and is not
offered inside a no-change window. See
[Rotate a credential: on a schedule](rotate#scheduled).

## The read-only account {#read-account}

The **Read-only account** card, below the profiles, holds a second account per device, for
reads only. **The AI's device reads sign in with it only under the hardened choice**: Settings ›
Installation › AI, the AI troubleshooting card's **AI device reads sign in as**, set to the
read-only account. By default they sign in as **Mercury's account**, exactly as Show commands
does, through the same protections and more (a read of one of the AI's command families,
held whole by the allowlist, its addresses and
interfaces checked against the device's golden and intent, the read loop's re-check, each read
on History › Reads with whom it signed in as). The read-only choice is offered only while every
device holds the account and its newest probe passed, and its Save names the devices that do
not. Under it, the AI's reads never escalate (no `enable`): they run at the account's own low
privilege, so the device limits what they may run as well as Mercury. A device's read-only
account is looked for
in the profiles' order (platform, kind, site, then default): the first profile that carries
one gives it. A device's own login and its network's credential list carry no read-only
account, and neither does a local inventory's devices file: a local inventory's device takes
its read-only account from the profiles by its kind, then default, as a NetBox one does (a
local inventory names no NetBox platform or site). **Under the read-only choice, a device none
covers is refused by name**, "no read-only account for <device>", and nothing is read from it;
the deploy account is never used instead.

Each profile's row names its **deploy account** (used by device-changing operations) and its
**read-only account**: the account's name, when its password was set and by whom, never the
password. **Resolves for** counts the devices every network holds (a NetBox inventory's as last
loaded, a local inventory's as its devices file lists them) that take their read-only
account from that profile; the line above the table says how many resolve one and
how many do not, and the group **no read-only account**, closed until opened, names those
that do not.

**Set the read-only account…** asks for the account's name and its password, which you type;
the name may not be the profile's deploy account's, and the password may not be the deploy
account's password. **Set the read-only account** saves them: the password is sealed in the
credential store like every credential, and masked by value wherever a device could echo it.
**Replace its password…** sets a new password under the same name: **an account is added,
never changed**, so a different name is refused, naming both. **Cancel** closes the form with
nothing changed. Each needs a verified person, and is recorded on History (Credential profiles):
who, which profile and which of the account's fields were set, never a value. Credential health
lists each read-only account by its age, as it lists the deploy accounts.

**What it may run** is the AI read set's show commands and bounded ping and traceroute, at a
low privilege level. **On the devices** says how the account reaches a device, which Mercury
does not read yet: as an intent change (an account added, never changed), deployed by a
person; its device-side shape (privilege 1) is measured on an IOS and an IOS-XE device before
the rest. The intent change is one `users` entry naming the profile's account by its reference,
`read-account:profile:<profile>` (for the default profile, `secret_ref:
read-account:profile:default`, with `privilege: 1`), and no name or password: a deploy takes
the account's name and its password from this card, in memory, and its preview shows the line
with the password masked (`username <account> algorithm-type scrypt secret
<redacted:read-account:profile:default>`). Privilege 1 is the device's default and it never
prints it, so the line leaves it out, and verify reads the account back as the device holds
it. A profile with no read-only account, or an entry naming a different account,
leaves the line without a value, and the deploy is refused by name before anything is sent. A
device that already holds an account of that name with another line is refused: the deploy
adds the account, never changes it. After its deploy verifies, Mercury keeps the device's own
form of the password for that device, so later deploys send nothing for it. Replacing the
password here changes no device: the devices keep the one they were given, and no operation
carries a new one to them yet. So **Replace its password…** is refused while a device whose
read-only account comes from this profile holds it (as **On the devices** last read its golden),
naming each device and when it was read, and while that coverage cannot be read; nothing is
saved. It is allowed while no device holds the account (C3427's first part; its rollout to
every device holding the account comes later).
Deleting a profile deletes its read-only account with it; retiring a device removes its intent,
and the account with it.

**Where privilege 1 misses a read**, the account moves to a custom privilege level and intent
names the reads that level may run. Measured on an IOS-XE router: privilege 1 answers the AI
read set's show commands and a plain ping, and refuses its telemetry reads and the options of
its ping and traceroute. The `users` entry then carries the level (`privilege: 3`, which the
line renders and the device prints, so verify reads it back), and a second key,
`privilege_exec`, holds one entry per read moved to that level:

    privilege_exec:
    - {level: 3, command: show telemetry ietf subscription, all: true}
    - {level: 1, command: show, all: false}

which a deploy sends, before the account's line, as four lines, the ones the device itself
stores for these two entries:

    privilege exec all level 3 show telemetry ietf subscription
    privilege exec level 3 show telemetry ietf
    privilege exec level 3 show telemetry
    privilege exec level 1 show

**A line moves a command for every account on the device**, not for this one alone, and its
leading words move with it. The first line lowers the telemetry read to level 3, with every
option under it (`all`: a subscription's id, `receiver`); that takes nothing from anyone. But
the device raises the command's leading words `show telemetry ietf`, `show telemetry` and
`show` to 3 as it takes the line, and every account below level 3 would lose every show
command. The device writes a line for each of those leading words, and Mercury's render
writes them too, so the device and its intent read the same. The last line puts `show` back
at level 1, so those accounts keep every show command they had, and only the telemetry
commands sit at 3. Mercury always sends the level-1 line after the lines it follows, whatever
their order in intent. On an IOS-XE device these are the read-only account's lines; on an IOS
device there are none, because what privilege 1 misses there is not measured yet.

Mercury holds an entry to an allowlist and refuses anything else by name when the intent is
saved. The level is 2 to 14. The command is a read of the AI read set, in the device's own
whole words (a show form, ping or traceroute, IPv6 forms beside IPv4), or the leading words
of one, as a device prints them back; never `configure`, `debug`, `clear`, `write`, `copy`,
`reload`, `enable` or `show running-config`. `all: true` writes the line's `all` keyword
(every option under the command moves with it), only on a read's whole words, never on `show`
alone. **Level 1 is held only as that restore**: for the leading words of another entry the
same intent holds at 2 to 14, without `all`. A level-1 entry alone, for `ping`, `traceroute`
or any read's whole words, or leading nothing the intent holds, is refused. A deploy adds
these lines and never removes one: a line taken out of intent stays on the device. A device
whose stored configuration already holds the account at privilege 1 is refused the change (an
account is added, never changed). Mercury never signs in to a parser view for these reads: a
view needs `aaa new-model`, which changes how every person signs in to the device.

**Ping and traceroute are not opened to the account by default.** Their options are
privileged on these devices, and the two lines that open them to level 3 (`privilege exec all
level 3 ping`, `privilege exec all level 3 traceroute`) **remove ping and traceroute from
levels 0 to 2 for every account on the device**, the plain `ping <address>` too. So it is an
installation choice, **Let the read-only account ping and traceroute**, off unless an admin
turns it on (the setting `ai_read_account_ping_traceroute`; it has no control on a Settings
screen yet, and is set in the settings file). While it is off, no such line is written, the
AI's ping is the plain `ping <address>` (the device's defaults, 5 echoes and a 2 second
timeout, so it measures the same and answers at privilege 1), and a ping from a named
interface or a traceroute is refused, naming the choice. With it on, the account's lines gain
those two, and their preview says what they remove.

## On the devices {#on-the-devices}

The card **Read-only account on the devices**, below the Read-only account card (board R,
provisional, operator review pending), says which devices hold the account, at which level, and
what its last probe said. It is read in the background, never by the page: from each device's
committed intent (its `users` entry naming `read-account:profile:<profile>`, and the level),
its committed golden (the `username <account>` line it holds as last captured, and its level:
a line naming no privilege is level 1, the device's default) and the newest record of the
read-only account probe for it. The summary leads, with when it was read ("checked 40 s ago"):
how many devices there are and how many are in each state, and how many probe records say
PASS, INCOMPLETE, FAIL or nothing. Never a password.

**Search devices**, **Network**, **Platform** and **Result** narrow the groups, and the summary
then says it is a subset and how many match. The groups are by state, each closed until
opened, the states to act on first:

- **can't be added**: the device's golden holds the account at another level than the
  account's (3). An account is added, never changed, so a deploy would refuse it.
- **no read-only account**: none of the device's profiles carries one. Set one first.
- **intent says it, not deployed yet**: its intent names the account and its golden does not
  hold it: the rollout deploys it.
- **not yet**: neither its intent nor its golden holds it.
- **on the device, not in intent**: its golden holds it at the account's level, its intent does
  not name it.
- **hold it at level 3**: both say it.

Each row: the device (opening its page), the network, the platform, **Intent says** (the
account and its level, or not yet), **Device holds** (the account and its level, not yet, or no
golden recorded), the level, **Last probe** (when, by whom, and the result, its reason on
hover; never probed when there is no record) and the state with why. An open group lists its
first 50 devices and says how many it leaves: search or filter to narrow. **Probe…**, on a row
whose intent names the account or whose device holds it, opens the probe's preview in place:
whom it signs in as, every command in order and what each is expected to answer, and its hash;
**Probe <device>** runs it as a verified person, holding the device, and the verdict is drawn in
place, kept by the device's identity, and listed on History under **Read-only account probes**
([Probe the read-only account](read-account-probe)). The Last probe column reads the newest
record of the device itself: a former device of the same name lends it none.

## Add the read-only account {#add-read-account}

**Add the read-only account…** opens the devices to tick, grouped by network, each with its
state as the coverage last read it; a device that holds it already, or cannot take it, cannot
be ticked. **All not yet (N)**, **Every device of <network>** and **Every <platform> device**
tick a group; **Clear** unticks. Give a **Reason** and press **Preview the intent change**: it
writes nothing. For each ticked device, its committed intent gains the account's `users` entry
by reference (`{privilege: 3, secret_ref: read-account:profile:<profile>}`, no name and no
password) and its level's `privilege_exec` entries for its platform (on IOS-XE the telemetry
line and the level-1 restore of `show`; on IOS none), as structured entries, never typed text.
The preview groups the devices with the same change and shows, for each group, the change in
words and the lines a deploy will send, in order, masked, each `privilege exec` line with what
it does to every other account on the device. While **Let the read-only account ping and
traceroute** is off, it says what turning it on would remove. A device is **refused by name**
when no read-only account resolves for it, its golden holds the account at another level (as
the coverage last read it; the deploy checks again), or the intent editor's checks refuse the
result. **Add to N devices' intent**, as a verified person, commits it through the intent
editor's own commit: one commit per network, `Source: read-account-add`, with your reason and
the preview's hash. If any device's intent moved since the preview, nothing is written and it
says so, naming both hashes. **Back** returns to the ticks, **Cancel** closes the card. The
result names each network's commit, says nothing was sent, and offers the rollout:
[Roll out the read-only account](read-account-rollout).

## Update the read-only account's lines {#update-read-account}

When the account's set of lines changes (on IOS-XE, the telemetry line became
`privilege exec all level 3 show telemetry ietf subscription`), a device whose committed intent
holds one of them in another form (another level, or without `all`) cannot simply take the new
one: Add never changes a held line in passing. Such a device can be ticked in **Add the
read-only account…**, its row saying how many lines are in another form, and Add's preview lists
it under **In another form** with **Update the read-only account's lines…**, which previews
that edit and writes nothing. For each device the preview names each line old → new and the
lines a deploy will then send, in order, masked; only the account's own lines change, and every
other line of the intent stays as it is. A device whose lines are the account's already is
named as current; one the intent editor's checks refuse is refused by name. **Update N
devices' intent**, as a verified person, commits it as Add does: one commit per network,
`Source: read-account-update`, with your reason and the preview's hash; a moved intent writes
nothing and names both hashes. Nothing is sent to a device: the rollout deploys it.
