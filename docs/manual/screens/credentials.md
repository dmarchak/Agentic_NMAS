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
- Needs attention's break-glass rows (**Export it on Credentials…**, **Record the drill on
  Credentials…**);
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
designated credential list, a role profile, a site profile, the default profile. v2 does not
yet draw which of these a device's credential came from: the device page's Credential check
shows its age and its rotation policy only (a gap, registered, C1360). Values are write-only:
none is ever shown back.

## Profiles {#profiles}

The **Profiles** tab lists the credential profiles, which apply to every network on this
installation. A device a NetBox inventory brings in carries no login of its own, so it is
given one in the order above; a local inventory's devices carry theirs in it and never read
a profile. Each row says which devices it gives its login to: `role:<role>` every device with
that role, `site:<site>` every device at that site, `default` every device nothing before it
covers. A profile under any other name is stored and read by nothing, and its row says so.
The password and enable secret are shown only as set or not set, and **Password last set**
says when the password was last changed.

**Add a profile…** asks what it covers (a role, a site, or every device), the username, the
password and, if its devices need one, the enable secret; a new profile needs the username and
the password. **Edit…** keeps any field you leave empty. **Delete…** says what the profile
covered and that those devices then take their login from the next source; one no source
covers is skipped by its next NetBox import, which says so. Each needs a verified person, and
each is recorded on History (Credential profiles): who, which profile, and the fields set,
never a value.

**Rotation policy…** on a profile's row sets how its devices' credentials are rotated on a
schedule: off, or every N days inside a preferred window of UTC hours, at most K devices a run.
It can name only some devices (a pilot), and says **why** the policy is as it is, one line
kept with it. Only a verified person sets one, and History records who, when
and the policy with its reason. The row's
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
without one, and Needs attention names the device and the stage. **Rotate due devices
now…** previews the devices it would take, and confirming runs them one at a time through the
device page's rotation, each row on the run's stepper in place. See
[Rotate a credential: on a schedule](rotate#scheduled).
