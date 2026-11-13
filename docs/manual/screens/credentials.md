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
reads only. **Every AI read signs in with it**, never with the deploy account, and never
escalates (no `enable`): the AI analysis's reads run at the account's own low privilege, so the
device limits what it may run as well as Mercury. A device's read-only account is looked for
in the profiles' order (platform, kind, site, then default): the first profile that carries
one gives it. A device's own login and its network's credential list carry no read-only
account, and neither does a local inventory's devices file: a local inventory's device takes
its read-only account from the profiles by its kind, then default, as a NetBox one does (a
local inventory names no NetBox platform or site). **A device none covers is refused by name**, "no read-only account for <device>",
and nothing is read from it; the deploy account is never used instead.

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
with the password masked (`username <account> privilege 1 algorithm-type scrypt secret
<redacted:read-account:profile:default>`). A profile with no read-only account, or an entry naming a different account,
leaves the line without a value, and the deploy is refused by name before anything is sent. A
device that already holds an account of that name with another line is refused: the deploy
adds the account, never changes it. After its deploy verifies, Mercury keeps the device's own
form of the password for that device, so later deploys send nothing for it. Replacing the
password here changes no device: the devices keep the one they were given, and the AI's reads
of them fail to sign in until the new one reaches them, which no operation does yet.
Deleting a profile deletes its read-only account with it; retiring a device removes its intent,
and the account with it.
