# Backups

A backup is a copy of one device's running or startup configuration, read from the device
when you ask and kept as a file on the host. It is a snapshot for reference: it is not
committed, carries no author, and nothing deploys or restores from it. Backups are on today's
app, on the device page's Backups tab.


## A backup and a golden {#vs-golden}

Both are a configuration captured from a device. They differ in everything that makes a
golden a record:

- **Where it lives.** A golden is committed in the network's repository and pushed to its
  remote. A backup is a file in the list's backups folder on the host, outside the
  repository, never committed and never pushed.
- **How it is made.** A golden is recorded only through a previewed, confirmed operation
  ([Capture](capture), a deploy, a restore) and says who recorded it and why. A backup is
  written the moment you press the button, by whoever is on the page.
- **What reads it.** Deploy, restore, drift and baselines read the golden. Nothing reads a
  backup to change a device. The template preview compares a device's golden with its newest
  backup, and builds from the backup only when the device has no golden.

## Taking a backup {#take}

1. **Choose the configuration and press Backup Config**: running or startup. Read: `show
   running-config` or `show startup-config`, on the device's pooled session, waiting up to 30
   seconds. Sent: nothing that changes the device. Recorded: a new file named
   `<hostname>_<address>_<running|startup>_<date>_<time>.cfg`, holding the configuration
   exactly as read (secrets included), and a row in the folder's index with its time, type
   and size. Two backups of one device in the same second get `_2`, `_3`, so neither replaces
   the other.

The page reloads on the Backups tab with a message naming the file, or the reason it failed.

Two other paths write a backup the same way: **Refresh capture** on the Templates screen
hands the device to this same button, and the AI assistant has a backup tool.

## History {#history}

The table lists this device's backups, newest first, up to 50, matched by the device's
address: the time, running or startup, the file name, its size, and Download and Delete. "No
backups found for this device" means the index holds none for that address.

## Compare {#compare}

**Compare Backups** opens a chooser: pick an older and a newer backup of this device. The
result is a line-by-line difference of the two files, or "The configurations are identical."
Every secret on either side is masked in the difference. Read: the two files. Sent: nothing.
Recorded: nothing.

## Download {#download}

The Download button asks for the **raw** file, so it needs a signed-in person, and every raw
download is recorded in the reveal record (who, when, which file). If the reveal is refused,
the answer is the masked text, never the secret beside an error. The same address without
asking to reveal returns the file masked, and records nothing.

## Delete {#delete}

Delete asks you to confirm, needs a signed-in person, removes the file and then its row in
the index. It cannot be undone, and nothing records who deleted it. Nothing else depends on a
backup, so deleting one never changes a golden, an intent or a device.

## What backups are not {#not}

- **Not a way back.** Nothing restores a backup to a device. To put a configuration back, use
  [Restore and re-apply a baseline](restore), which previews the exact program first.
- **Not the record.** A backup says what the device held at one moment, never what it
  should hold: that is its intent, and what it was last recorded holding is its golden.
- **Not pruned.** Backups accumulate until someone deletes them.
- **Per list.** Each list has its own backups folder; the list the app is showing is the one
  read and written.
