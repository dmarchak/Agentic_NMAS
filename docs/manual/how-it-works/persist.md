# Persist

A device boots from its startup configuration, not from what it runs now. Persist saves the running configuration to startup on the device and proves it was saved, so a reload brings the device back as it is, with the credential the tool holds. It changes no configuration and writes nothing in the tool except a record of what the device answered.

![Persist from the device page: the plan reads only the tool's own records and sends nothing, and the card then reads what saving changes; the apply holds the device, sends write memory, reads the startup and running configurations back, and records the outcome where job health reads it. A rotation's persistence is the same save and read-back.](diagrams/persist.svg)

There are two paths that persist a device, and they do the same thing to it:

- **Persist on the device's page** (Actions > Persist, its card in place of the tab), and `nmas-persist-native` on the host: the device's own save and its read-back, and nothing else. The page's card calls the plan and apply (`/v2/device/<name>/persist` and its confirm). This is the page's subject.
- **A rotation's persistence** (`credential_rotation.persist()`): run after every rotation, from the device's page or `nmas-rotate-credential`, and by `nmas-persist-credential` to finish one. It is the same save and read-back; see [after a rotation](#the-host-chain).

## The preview

The plan contacts no device. Read: the list's registry, the device's inventory row (its address, Netmiko driver, account and stored credential) and the hourly startup check's last reading for the device, with its age. Sent: nothing. Recorded: nothing. It refuses, each as a named gate, a list that does not exist, a device not in that list's inventory, a row with no driver recorded and a row with no stored credential. You confirm the plan's hash, which binds the list, the device, its address, its driver and its account.

**What saving changes in what it boots.** Once the plan can run, the card reads the device as a job, the same reads Reload's check makes. Read: the running configuration, `show startup-config`, and `dir nvram:` only when startup keeps a certificate as a file there. Sent: nothing but those show commands. Recorded: nothing. It compares the two as Reload's "running against startup" check does: `show startup-config`'s "Using N out of M bytes" line is not a difference, and a certificate startup keeps as a file in nvram: is the same certificate running prints inline, when `dir nvram:` lists the file. It lists the lines startup gains (only running holds them) and the lines it loses (only startup holds them, gone at the next reload), masked; names any certificate file `dir nvram:` does not list; and, when the two are the same, says so and that Persist still saves (`write memory`) and reads startup back. The confirm does not wait for it: what is sent is the save either way.

## The apply, in order

The apply holds the device, so no other operation runs on it meanwhile, and the plan is computed again first: a different hash refuses with nothing sent.

1. **Save** (`save`). Read: nothing. Sent: the device's own save, `write memory` (Netmiko's save for the device's driver, after entering enable mode), on a session signed in with the credential the inventory holds. Recorded: nothing yet. The startup configuration becomes a copy of the running configuration as it is now.
2. **Read back** (`read_back`). Read: `show startup-config`, then `show running-config | include ^username`, on the same session. Sent: nothing. Recorded: nothing yet. The device is persisted only if the startup configuration carries every `username` line the running configuration has, verbatim; a startup configuration that is absent, or missing one of them, is "not persisted", and a running configuration with no `username` line at all is "unknown". The comparison is with the running line, never with what was sent, because a type 9 secret is salted and cannot be recomputed.
3. **Record** (`record`). Read: nothing. Sent: nothing. Recorded: a row in the rotation record (`via: device page`, as you), with the save's own state: `persisted` when the read-back matched, `saved_not_persisted` when the startup config lacks a credential line the running one holds, `save_unverified` when the save or its read-back could not run. A save never records a rotation's state, since it rotates nothing; each credential line is named by its form, never its value. Job health's rotation row reads that record, so its "would boot the wrong credential" row clears only on a read-back that matched; so does Needs attention's row for a deploy that was verified and NOT saved to startup, which clears on a `persisted` row recorded after the deploy. The device's [History](device-page#history-tab) draws the row as a persist ("Persisted: the startup config carries the running credential"), with you and the path, opening its steps.

`nmas-persist-native <device> --list <list>` runs the same three steps from the host shell, holding the device the same way, and records the row as `via: nmas-persist-native`.

## After a rotation {#the-host-chain}

`credential_rotation.persist()` is what a rotation runs after it records the new password, and what `nmas-persist-credential` runs to finish a rotation whose persistence stopped. `nmas-persist-credential` first checks that the inventory's credential still signs in (a fresh login) and that committed intent carries the device's type 9 secret, and refuses otherwise. It has one stage, which may find its work already done:

1. **The device's own save** (`device_startup_config`). Read, Sent and Recorded: as steps 1 and 2 above, and the rotation record's row says rotated and persisted only when the read-back matched. A reload boots the device's own startup configuration, so that is what is proved.

The rotation's own commit is the record of the new credential, and it writes the *golden committed* event (`<data>/events/golden-committed/<network>`, naming the devices). Where a device boots from a file built elsewhere, the tool that builds it waits on that event, so the file carries the new credential; Mercury itself writes no such file. (The chain once had more stages: Oxidized's, gone with Oxidized on 2026-10-08, and the startup-file stages of emulated devices, gone from the product on 2026-10-11.)

## What persist does not do

- It changes no configuration: the save carries the running configuration exactly as it is, including anything not yet recorded as a golden.
- It rotates no credential.
- It writes no boot file anywhere but the device itself.
- It commits no golden: the running configuration is not captured into the record.
- Nothing re-reads the device's startup configuration until the hourly startup check runs; that check is what notices a later change.
