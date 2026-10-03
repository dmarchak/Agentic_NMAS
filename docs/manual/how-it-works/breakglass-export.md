# Export the break-glass record

The break-glass record is the way back into the devices when the tool cannot sign in to them,
and the way back to the stored secrets if the host loses its application key. The export
builds one sealed file holding every device's credential in one list, and the application
key, and hands it to your browser as a download. It contacts no device and changes no
credential. On the host it writes two rows that say an export was made, and never the file.

![The tool reads the list's credentials and the application key, seals them with your passphrase, opens the sealed file again to check it, records the reveal and the export, and sends the file to your browser; no device is contacted.](diagrams/breakglass-export.svg)

## Where to open it {#open}

One operation, reached from four places:

- **Settings**: the Export button, for the list the app is showing.
- **Needs attention**: the break-glass row, when no export is logged for a list or a device's
  credential has changed since the last one.
- **The result of a rotation**, as its next step: the record still holds the old password.
- **The result of an adoption**, as its next step: the record does not hold the new device.

On the redesigned pages each of these opens the export itself, for the list it names, never a
page you then have to search: until the export is on those pages, it opens on today's pages,
already showing what the record would hold.

Exporting needs a signed-in person. A service is refused, because the file holds every
device's credential.

## The preview {#preview}

1. **What the record would hold**. Read: the list's inventory with each credential decrypted
   in memory, the application key file (read only, never created), and the values the
   application has stored encrypted, to count how many the key opens. Sent: nothing. Recorded:
   nothing. The preview names each device with its address and platform, says which have no
   stored password (they are recorded without one) and which have a separate enable secret,
   and shows the key's fingerprint and how many stored values it opens; no credential is shown.

The gates are drawn by name: the list holds devices, and the key can be read. Four more are
checked when you confirm: the passphrase, the credentials unchanged since the preview, the
finished record verifying, and the reveal being recorded. The preview carries a hash of the
credentials and the key, and the confirm is bound to it.

## The export {#export}

You type a passphrase twice and confirm. The fields are cleared the moment the request
leaves the page. Then, in order:

1. **The passphrase is checked** (`passphrase`). Read: nothing. Sent: nothing. Recorded:
   nothing. The two entries must match and be at least 12 characters, because the file is an
   offline target that can be attacked at leisure; otherwise nothing is built.
2. **The plan is computed again** (`plan`). Read: the inventory and the key, as in the
   preview. Sent: nothing. Recorded: nothing. If its hash differs from the one you confirmed
   (a rotation since the preview, most likely), the export is refused and you preview again.
3. **The record is built and sealed** (`build`). Read: each device's hostname, address,
   username, password, enable secret, platform and container, and the application key. Sent:
   nothing. Recorded: nothing, the file exists only in memory. A key is derived from your
   passphrase with scrypt and the record is encrypted with it; the salt travels in the file
   and the passphrase does not.
4. **The sealed file is opened and checked** (`verify`). Read: the finished bytes, opened with
   your passphrase, and the stored values again. Sent: nothing. Recorded: nothing. Each
   device's login credential must match what was put in, no device that had a password may
   have lost it, the escrowed key must be the application key, and it must open as many
   stored values as the application key does. Any difference refuses: nothing is sent.
5. **The reveal is recorded** (`record`). Read: nothing. Sent: nothing. Recorded: a reveal
   row with who, when, the list, the device count and the file's sha256. If the row cannot be
   written, nothing is sent: this action never happens unrecorded.
6. **The export is logged**. Read: nothing. Sent: nothing. Recorded: a row in the export log
   with the time, the list, "downloaded by" you, the key's fingerprint, the sha256 and one
   salted digest per device, never a value. If this row cannot be written the file is still
   sent, and the result is drawn as partly done, because the tool then cannot tell when the
   record goes stale.
7. **The file is downloaded**. Read: nothing. Sent: the sealed file, to your browser only.
   Recorded: nothing more. It is named after the list and the time, ending `.bg`.

The result says what the record holds, what was verified (the device count, the key's
fingerprint and how many stored values it opens, the sha256), and, as an optional next step,
how to verify the copy where you keep it.

## What the record holds {#contents}

For each device in the list: its hostname, address, username, password, enable secret,
platform, list and container. Beside them: the application key, a short written recovery
procedure, and when the record was made. Anyone holding the file and the passphrase can read
every one of these, so keep the two apart.

## What it does not do {#not-done}

- It never writes the file to the host's disk: built, sealed and verified in memory, then
  sent. There is nothing to clean up.
- It never stores, logs or returns the passphrase, and it appears in no error. Nothing can
  recover it.
- It contacts no device and changes no credential.
- It cannot see where the file goes after it leaves. A download that was lost reads exactly
  like one that was kept.
- The check compares each device's login credential (username and password). The enable
  secret is carried in the record and is not compared.
- It covers one list. Each list is exported on its own.

## Keeping it current {#current}

The record holds the credentials as they were when it was made, so every rotation makes it
older. Job health compares the newest export logged on this host with the credentials the
tool holds now, list by list, using the same salted digests, and no value moves:

- A device whose credential changed since the export, or that joined the list since, is a
  danger row on [Needs attention](needs-attention): the record cannot recover it. Its action
  opens this export.
- A list with no export logged is a row saying nothing establishes whether the record is
  current, with the same action.
- When every device is current, the row says so and asks you to verify the copy you keep,
  because the host knows the export was sent and never whether it survived.

To verify a copy where you keep it, without moving a credential:

```
on the host:        nmas-breakglass digests --list <list> > digests.json
beside the record:  nmas-breakglass verify <file> --against digests.json
```

It names each device current, different, missing or no longer managed, prints no value and
contacts no device.
