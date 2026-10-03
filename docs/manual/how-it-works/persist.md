# Persist

A device boots from its startup configuration, not from what it runs now. Persist saves the running configuration to startup on the device and proves it was saved, so a reload brings the device back as it is, with the credential the tool holds. It changes no configuration and writes nothing in the tool except a record of what the device answered.

![Persist from the device page: the preview reads only the tool's own records and sends nothing; the apply holds the device, sends write memory, reads the startup and running configurations back, and records the outcome where job health reads it. The host chain that a rotation runs adds the lab's Oxidized and startup-file stages after the same save.](diagrams/persist.svg)

There are two paths that persist a device, and they differ in what they touch:

- **Persist on the device's page** (Actions > Persist on the redesigned page, its card in place of the tab; Persist… on today's page), and `nmas-persist-native` on the host: the device's own save and its read-back, and nothing else. The two pages call the same plan and apply (`/v2/device/<name>/persist` and its confirm, `/persist/preview` and `/persist/apply`). This is the page's subject.
- **The host chain** (`credential_rotation.persist()`): run after every rotation, from the device's page or `nmas-rotate-credential`, and by `nmas-persist-credential` to finish one. It does the same save first, then updates Oxidized and the lab host's startup file. Those stages are a lab integration; see [the host chain](#the-host-chain).

## The preview

The preview contacts no device. Read: the list's registry, the device's inventory row (its address, Netmiko driver, account and stored credential) and the hourly startup check's last reading for the device, with its age. Sent: nothing. Recorded: nothing. It refuses, each as a named gate, a list that does not exist, a device not in that list's inventory, a row with no driver recorded and a row with no stored credential. You confirm the plan's hash, which binds the list, the device, its address, its driver and its account.

## The apply, in order

The apply holds the device, so no other operation runs on it meanwhile, and the plan is computed again first: a different hash refuses with nothing sent.

1. **Save** (`save`). Read: nothing. Sent: the device's own save, `write memory` (Netmiko's save for the device's driver, after entering enable mode), on a session signed in with the credential the inventory holds. Recorded: nothing yet. The startup configuration becomes a copy of the running configuration as it is now.
2. **Read back** (`read_back`). Read: `show startup-config`, then `show running-config | include ^username`, on the same session. Sent: nothing. Recorded: nothing yet. The device is persisted only if the startup configuration carries every `username` line the running configuration has, verbatim; a startup configuration that is absent, or missing one of them, is "not persisted", and a running configuration with no `username` line at all is "unknown". The comparison is with the running line, never with what was sent, because a type 9 secret is salted and cannot be recomputed.
3. **Record** (`record`). Read: nothing. Sent: nothing. Recorded: a row in the rotation record (`via: device page`, as you), with the state persisted when the read-back matched and unverified otherwise; each credential line is named by its form, never its value. Job health's rotation row reads that record, so its "would boot the wrong credential" row clears only on a read-back that matched.

`nmas-persist-native <device> --list <list>` runs the same three steps from the host shell, holding the device the same way, and records the row as `via: nmas-persist-native`.

## The host chain {#the-host-chain}

`credential_rotation.persist()` is what a rotation runs after it records the new password, and what `nmas-persist-credential` runs to finish a rotation whose persistence stopped. `nmas-persist-credential` first checks that the inventory's credential still signs in (a fresh login) and that committed intent carries the device's type 9 secret, and refuses otherwise. Each stage gates the next, and every stage may find its work already done:

1. **The device's own save** (`device_startup_config`). Read, Sent and Recorded: as steps 1 and 2 above. Done first because a reload boots the device's own startup configuration, whatever happens to the lab's copy.
2. **Oxidized's row** (`oxidized_row`, lab integration). Read: nothing from the device. Sent: nothing to the device. Recorded: the device's row in Oxidized's router.db, written by a root-owned helper run through `sudo -n`, the password passed on standard input. Oxidized signs in with the new password from now on.
3. **Oxidized re-reads it** (`oxidized_reload`, lab integration). Read: Oxidized's node list, until it is served again. Sent: `GET /reload` to Oxidized. Recorded: nothing. Writing the file is not enough on its own.
4. **A fresh fetch** (`fetch_confirmed`, lab integration). Read: Oxidized's node list, until a successful fetch of the device ends after the chain began. Sent: Oxidized's "fetch this node next" request; Oxidized then signs in to the device and reads it. Recorded: nothing. "Requested" and "succeeded" are different events.
5. **Which lab** (lab integration). Read: the device's lab from the lab map (host, startup-file folder, launch script). Sent: nothing. Recorded: nothing. A lab that names no folder or no launch script is refused rather than reading another lab's.
6. **The lab sync** (lab integration). Read: nothing directly. Sent: nothing to the device. Recorded: the sync script runs, and writes each lab device's startup file on the lab host from the list's newest earned baseline, with every credential taken from the current golden (which the rotation's commit just updated).
7. **The new hash is in the file** (`startup_file`, lab integration). Read: a search of the device's startup file on the lab host for the new hash, over SSH. Sent: nothing. Recorded: nothing.
8. **The file would apply** (`startup_applies`, lab integration). Read: the lab's launch script, for the skip that stops the emulator injecting its own user ahead of the file. Sent: nothing. Recorded: nothing. A file can carry the right hash and still not be what the device ends up holding.
9. **The checker's verdict** (`startup_safe`, lab integration). Read: the startup file's account line against the device's current golden, and the applicability again. Sent: nothing. Recorded: the chain's row in the rotation record, state rotated and persisted only when this reads SAFE. It is the same judgement as `nmas-check-startup-applies`, so the two cannot disagree.

On an installation without the lab, stage 1 still saves the device, and stage 2 fails (no helper), so a rotation ends "rotated, persistence unverified" and job health keeps the device in front of you. Persist… on the device's page is then the way to record the device's own save.

## What persist does not do

- It changes no configuration: the save carries the running configuration exactly as it is, including anything not yet recorded as a golden.
- It rotates no credential.
- From the device's page, it writes neither the lab host's startup file nor Oxidized's router.db; the host chain above does.
- It commits no golden: the running configuration is not captured into the record.
- Nothing re-reads the device's startup configuration until the hourly startup check runs; that check is what notices a later change.
