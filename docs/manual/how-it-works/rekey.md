# Re-key a device: its SSH host key

Every SSH server proves who it is with its host key. {{product}} keeps each device's key the first time it meets it, and from then on compares the key a device presents with the one it keeps, before it signs in. A different key is refused: nothing is sent, so the device's credential never reaches whatever answered. A device rebuilt from a fresh disk legitimately answers with a new key; Re-key is how a person reviews it and keeps it.

![Re-keying a device. Every session compares the SSH host key the device presents with the one held, before any credential is sent: the first contact keeps it, a different key is refused naming both. The re-key's preview reads the key the device presents now with no credential and shows it beside the held one, with any restart recorded since. You confirm both keys. The apply holds the device, reads the key again and keeps nothing if it moved, replaces the held key, reads the record back, and keeps the old key in the record's history.](diagrams/rekey.svg)

## Every session, first {#every-session}

Every session to a device opens through one place, and its key is compared there, after the key exchange and before any credential is sent. This covers every operation, every reader and every host script that signs in to a device, and the NETCONF push (which compares against the same record and never keeps a key of its own).

- **First contact.** No key is held for the device's address (none was ever kept, or the one kept was forgotten when its device was [retired](retire) or its onboarding [abandoned](onboard#between-the-phases-the-device-boots)): the key it presents is kept, with its type, its fingerprint (SHA256, as `ssh-keygen -l` prints it), when, and who: the operation holding the device and its person, or the reader or script that opened the session, said as no verified person when there is none.
- **The same key.** The session signs in.
- **A different key.** Refused, naming both fingerprints: "r1 answered with SSH host key SHA256:… where {{product}} holds SHA256:… (kept … by …): nothing was sent." The refusal is the operation's own answer (its card, a reader's row), and a Needs attention row names the device until a session finds the key it holds.
- **The record cannot be read.** Every session is refused, naming the record: no key could be compared, and keeping one over an unreadable record would lose every key it held.

The record is one file in the data folder, `ssh_host_keys.json`, owner-only, keyed by the address {{product}} connects to (as OpenSSH's `known_hosts` is): onboarding meets a device before it belongs to a network, and one address names one machine whatever network lists it.

## A lab redeploy: keys declared in advance {#planned-window}

A device redeployed from a fresh disk generates a new key as it boots, so every device of a redeploy answers with a new key. Rather than a re-key per device, the redeploy says so when it declares its planned-restart window: `nmas-planned-restart <list> '*' --minutes 45 --why "lab redeploy" --new-host-keys`, or `"new_host_keys": true` in the body a redeploy script sends to the planned-restart API. Inside that window (and up to 15 minutes after it), the first new key each covered device answers with is kept, recorded as kept under the window and naming who declared it. A window accepts one new key per device; a key {{product}} had already refused before the window was declared is never accepted by it (that key needs a person's review here); and a key that changes outside any such window is refused. A Reload declares no such expectation: a reload keeps the device's key.

## The preview

Opened from the Needs attention row, or with `?op=rekey` on the device's page. Read: the list's registry, the device's inventory row (its address), the key {{product}} holds, the restart record, and the key the device presents now, read in the key exchange with no credential. Sent: nothing. Recorded: nothing. It shows the two keys first, then what is known of why the key changed: a restart recorded since the key was kept, planned or not, or that no restart was recorded, which is what something else answering at the address looks like. It refuses, each as a named gate, an unknown list, a device not in its inventory, an unreadable record, a device with no key held (its next session keeps one), a device that did not answer, and a device answering with the key already held. You confirm the plan's hash, which binds the device, its address and both fingerprints.

## The apply, in order

The apply holds the device, so no other operation runs on it meanwhile.

1. **Read the key again** (`read`). Read: the key the device presents now, with no credential. Sent: nothing. Recorded: nothing. The plan is computed again: a different key, or a record that moved, gives a different hash and refuses with nothing kept, naming both.
2. **Keep it** (`keep`). Read: the record. Sent: nothing. Recorded: the new key in place of the held one, as you, only if the held key is still the one the preview showed.
3. **Verify** (`verify`). Read: the record, read back. It holds the new key, or the result says it does not.
4. **Record** (`record`). The record keeps the old key in its history, with who replaced it, when and why (the restart evidence the preview showed). The device's [History](device-page#history-tab) draws each key kept: on first contact, re-keyed, or kept under a planned window.

## What the re-key does not do

- It sends nothing to the device and uses no credential: the key is read in the key exchange, before any sign-in.
- It changes no configuration, on the device or in the repository.
- It changes no other device's key.
- It does not forget the old key: the record keeps it.
