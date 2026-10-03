# Export the break-glass record

The break-glass record is the way back into the devices when the tool cannot sign in to them,
and the way back to the stored secrets if the host loses its application key. The export
builds one sealed file holding every device's credential in one list, and the application
key, and hands it to your browser as a download. It contacts no device and changes no
credential. On the host it writes two rows that say an export was made, and never the file.

![The tool reads the list's credentials and the application key, seals them with your passphrase, opens the sealed file again to check it, records the reveal and the export, and sends the file to your browser; no device is contacted.](diagrams/breakglass-export.svg)

## Where to open it {#open}

One operation, reached from four places:

- **Credentials**: the break-glass record's **Export the record…**.
- **Needs attention**: the break-glass row, when no export is logged for a list or a device's
  credential has changed since the last one.
- **The result of a rotation**, as its next step: the record still holds the old password.
- **The result of an adoption**, as its next step: the record does not hold the new device.
- **Settings**: its break-glass line links to Credentials.

Each opens Credentials › The break-glass record, with the export ready and showing what the
record would hold, for the list it names.

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
8. **The browser checks what it received** (`intact`). Read: the bytes, in your browser.
   Sent: the browser's sha256 of them. Recorded: a row with the list, both sha256s, whether they
   match, and you. Before saving the file, the browser hashes the bytes it received and
   compares them with the sha256 the server recorded. The result card then reads
   **Downloaded intact** or, in danger, **Not intact**, naming both sha256s. A download that
   did not arrive intact is not counted as current: delete it and export again. The browser
   computes a hash only on a secure page. Opened any other way, the result says
   **Not checked**, and the export is not counted either.

The result says what was built and sent, whether it arrived intact, what was recorded, and what
is still true.

## What the record holds {#contents}

For each device in the list: its hostname, address, username, password, enable secret,
platform, list and container. Beside them: the application key, a short written recovery
procedure, and when the record was made. Anyone holding the file and the passphrase can read
every one of these, so keep the two apart.

## Check a break-glass file {#check}

The copy you keep is the only one, and the host never sees it. **Check a break-glass file…**,
on Credentials and on the export's result, opens the copy here and says whether it still
recovers every device. You choose the file and type its passphrase. Then:

1. **The file is opened in memory** (`open`). Read: the file you chose, and its passphrase.
   Sent: nothing. Recorded: nothing yet. A file that is not a break-glass record, a wrong
   passphrase, or a file sealed for another list is refused, naming why, and nothing is
   compared.
2. **Each credential is compared** (`compare`). Read: the list's credentials in use, decrypted
   in memory. Sent: nothing. Recorded: nothing yet. The comparison is by salted digest, as job
   health compares, and no value moves.
3. **The verdict is recorded** (`record`). Read: nothing. Sent: nothing. Recorded: who, when,
   the file's sha256, when it was made, and the verdict per device and for the key; never a
   credential. The opened file is discarded.

Each device in the verdict reads one of these:

- **current:** the file recovers it;
- **not current:** rotated since the file was made;
- **not in the file:** managed now, and absent from the file;
- **no longer managed.**

The key reads **current** when it is the key in use. A copy that cannot recover a device, or
holds another key, says so in danger, with **Export the record again…**. Each check is a row in
History.

## The offline drill {#drill}

Only a drill proves the record opens without the tool: on the machine that keeps the file,
with nothing of the tool running. Credentials shows when the last one was done and when the
next is due, every 90 days. Needs attention raises a row only once it is overdue. To do it:

1. **On the machine that keeps the file**, run the command Credentials shows (**Copy** puts it
   on the clipboard) with the .bg file you kept: `nmas-breakglass drill <the .bg file you
   kept>`. The host never sees what the file is called where you keep it, so Credentials gives
   only the name the newest export was given when it was downloaded, labelled as that; it may
   have been renamed or moved since. Read: the file and its passphrase,
   typed at the terminal. Sent: nothing. Recorded: nothing. It opens the file, names the
   devices it can recover and prints one receipt line: the list, the file's sha256, when it
   was made, how many devices it recovers, the key's fingerprint and when it was opened. It
   prints no credential and no key.
2. **Paste the line into Credentials** and choose **Record the drill** (`record`). Read: the
   export log. Sent: nothing. Recorded: the drill (who, when, the file's sha256, the device
   count; no credential). The line must name this list and a file this host exported, with
   that export's device count and key. Anything else is refused, naming what the receipt said
   and what the log holds.

A recorded drill clears the overdue row and starts the next 90 days. Each drill is a row in
History.

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
