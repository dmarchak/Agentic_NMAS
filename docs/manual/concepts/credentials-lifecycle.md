# Credentials: rotate and persist

A device's login credential is not one value in one place. The device holds it twice (what
it accepts now, and what it will accept after a reload), the tool holds it in its own
stores, and copies of it travel: into git, into a sealed record on a person's laptop, and in
a lab, into the files a redeploy boots. A rotation changes the device and the tool's record
together; persist makes the device's startup configuration carry it; and every other copy
has to be brought along, or it becomes the copy that locks someone out.

![Where a device's credential lives: the device's running and startup configuration on the right; the tool's inventory, credential store and git repository on the left; the break-glass record on a person's laptop; and, in a lab, Oxidized's copy and the lab startup file. A rotation moves the running configuration and the tool's record together, persist copies running to startup, and an export renews the break-glass record.](diagrams/credentials-lifecycle.svg)

## Where it lives {#where}

On the device:

- **The running configuration**: the `username` line the device accepts now. After a
  rotation it is a type-9 secret, a salted hash the device generated itself.
- **The startup configuration**: what the device boots. Until it is saved, a reload brings
  back the old line, and the tool is locked out of a device it manages.

In the tool:

- **The inventory**: the password the tool signs in with, encrypted, on the device's row.
  For a device still being onboarded (no row yet), the same value lives in the device
  override store, keyed on its address.
- **The credential store**: the device's own hash, under a key naming the network, the
  device and the reference (`user_<account>_secret`). Intent names the reference, never the
  value, so a deploy renders exactly the line the device holds.
- **The repository**: the golden carries the hash line as captured. Every older golden and
  every baseline carries the line of its own moment.
- **A staged copy**, only during a rotation: the new password, encrypted, written before
  anything is sent and removed only once the record is written.

Away from the tool:

- **The break-glass record**: a file sealed with a passphrase, kept on a person's laptop,
  holding each device's credential and the application's key. It is how a person reaches a
  device when the tool cannot. It is current only until the next rotation.
- **Oxidized's copy** (lab integration): the account Oxidized polls with, in its router
  list, and the configuration it last fetched.
- **The lab startup file** (lab integration): the file a lab redeploy boots, built from the
  newest earned baseline with every credential line taken from the device's current golden,
  so a redeploy never boots a retired password.

## A rotation moves the device and the record together {#rotate}

Rotation is one operation, run as a job that holds the device from start to finish (see
[Rotate a credential](rotate) for the screen):

1. **Preflight**. Read: the account's line, live from the device. Sent: nothing. Recorded:
   nothing. The program depends on what the device holds now, not on a stored capture.
2. **Generate and stage** (`stage`). Read: nothing. Sent: nothing. Recorded: the new
   password, encrypted, in the repository's staging area. If anything later fails, this is
   the copy that saves the device.
3. **Push** (`push`). Read: nothing. Sent: one account line, on a session already open and
   proven. Recorded: nothing yet.
4. **Verify on a fresh login** (`verify_new_credential`). Read: a new SSH login with the new
   password. Sent: nothing. Recorded: nothing. If it fails, the old line is put back on the
   held session and proven; this is the only failure that reverts the device.
5. **Record** (`commit`). Read: the running configuration, for the device's new hash.
   Sent: nothing. Recorded: the new password on this device's inventory row only (never a
   shared profile), the device's hash in the credential store, intent's reference, and the
   golden with intent in one commit (`Source: rotation`). Only then is the staged copy
   removed.
6. **Persist** (`device_startup_config`). Read: the startup configuration, after the save.
   Sent: the device's own save. Recorded: the outcome, in the rotation record that job
   health reads. A rotation that is not persisted is a row until a later persist reads back
   correctly.
7. **The lab copies** (`oxidized_row`, `oxidized_reload`, `fetch_confirmed`, the lab sync,
   `startup_file`, `startup_applies`, `startup_safe`) (lab integration). Read: Oxidized's
   fetch and the lab startup file. Sent: nothing to the device. Recorded: Oxidized's router
   row and the lab startup files. Each stage gates the next.

A failure after step 5 never reverts the device: the rotation has happened and is recorded,
and only a copy is behind. The result names that state and its next step.

## Persist: the startup configuration {#persist}

A device boots from its startup configuration. Persist runs the device's own save, then
reads the startup configuration back: the device counts as persisted only if the startup
configuration carries every `username` line the running configuration has, verbatim. The
running line is the reference, because a salted hash cannot be recomputed from the password.

Persist is the last step of every rotation and onboarding, and a screen of its own on the
device page (see [Persist](persist)). On its own it changes no configuration and writes no
lab file.

## The startup check {#startup-check}

Every hour, `scripts/nmas-startup-check` signs in to every device with the credential the
tool holds and reads two things: the startup configuration, and the running configuration's
`username` lines. It never saves. Each device reads one of:

- **persisted**: the startup configuration carries every account line;
- **not persisted**: a reload would boot a credential the tool does not hold. This is the
  row with the most urgent action: persist the device;
- **unknown**: the device could not be read this hour, said as its own row, never as a
  failure of the whole check.

[Needs attention](needs-attention) draws each not-persisted device with Persist as its
action.

## The break-glass record after a rotation {#breakglass}

The break-glass record is sealed off the host, so the tool cannot open it. What it can do is
compare: every export logs a salted digest of each device's credential (never the value),
and job health compares the newest export's digests with the credentials held now. A device
rotated since the export reads **stale**, "the record holds an older credential: rotated
since", and the row's action opens the export. Export again after every rotation, and verify
the copy on the machine that keeps it: the host logs that an export was made, never where the
file went. See [Break-glass export](breakglass-export).

## What a deploy or restore does to a credential {#deploy}

- **A deploy may add an account; it may never change one.** A line that would rewrite an
  account the device holds is refused before anything connects, naming the form and never
  the value.
- **A restore is held to the same rule**, and to one more: a secret the chosen moment had
  and the device no longer has (an old community, a removed account) is held back until a
  person authorises it with a reason. So a baseline older than a rotation can still be
  re-applied for everything else, and is judged unusable for the devices it would rewrite
  (see [How a baseline is earned](baselines#decay)).

## What rotation does not do

- It does not rotate a shared credential profile: only the one device's row changes.
- It does not touch the break-glass record. That is a person's export.
- It does not revert the device for a failure to update a copy: only a failed fresh login
  reverts.
