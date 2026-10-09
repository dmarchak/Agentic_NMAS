# Save to startup and as golden

A device boots from its startup configuration, and the tool's record of it is its golden. Save makes the two the same for the devices you choose: each device saves its running configuration to startup (its own `write memory`), the startup is read back, and the running configuration is recorded as its golden, one commit for the batch. No running configuration is changed, so what the tool records and what a reboot brings back are the same.

![Save, from Devices: the plan reads only the tool's own records and sends nothing; you confirm its hash; each device is held, saves and is read back; the ones that matched are read for their running configuration and recorded in one commit, as you.](diagrams/save.svg)

Save runs from [Devices](devices): tick devices and choose **Actions › Save (N)…**, or **Save every device of the network…** from the same menu. It opens Devices › Save, the plan, with its confirm.

It is built from two operations that already exist, never a third copy of either: the device-side save and read-back are [Persist](persist)'s, and the record is [Capture](capture)'s.

## The plan

1. **Plan** (`plan`). Read: the network's inventory (each device's address, driver, account and stored credential), the hourly startup check's last reading, the reachability reader's last reading and the holds. Sent: nothing. Recorded: nothing. Each device chosen goes into one group:
   - **to save**;
   - **not answering: left out**, when the last reachability reading had it not answering;
   - **held by another operation: left out**, naming that operation and who runs it;
   - **cannot be saved from here: left out**, when it is not in the inventory, has no driver recorded or has no stored credential.

   The summary counts each group. For the devices to save, it says what the hourly startup check last read: whether each one's accounts (its `username` lines) were in startup. That check compares the accounts only, so whether the rest of startup differs from running is not measured; every device to save is saved whatever the check read.
2. **Confirm** (`confirm`). You confirm the plan's hash, as yourself. The hash binds each device to save with its address, driver and account. A plan that moved before the run (an address, a driver, an account, a hold or reachability) is refused with nothing sent; open Save again.

## The run, in order

The run is a job: the page can close, and the card redraws in place as each device ends and when the run finishes, never on a timer.

Before anything is sent, a device the network's manifest does not know (never onboarded or adopted) is left out, named: its golden would have nothing to attach to. Then each device runs on its own worker, at most eight at once:

1. **Hold** (`hold`). The device is held for `save`, so no other operation runs on it meanwhile. A device another operation took first is left out, named with its holder; the rest go on.
2. **Save** (`save`). Sent: the device's own save, `write memory`, on a session signed in with the credential the inventory holds.
3. **Read back** (`read_back`). Read: `show startup-config`, and the running configuration's `username` lines, on the same session. The device is persisted only if startup carries every one of them, verbatim. Recorded: a persist row in the rotation record, as you (`via: save`), the same row [Persist](persist) writes, so job health's rotation row and the device's History read it. A device whose read-back did not match was saved, but is **not recorded**: the record would claim what a reboot would not bring back.
4. **Read running** (`read_running`). Read: the device's running configuration, by Capture's own read, judged as one configuration, while the device is still held, so what is recorded is what it ran when it saved. A read that fails is named, and that device is not recorded.
5. **Release** (`release`). The device is released, however its turn ended.

When every device has had its turn:

6. **Record** (`record`). Recorded: one commit of every golden that changed, as you: `Source: save` for a selection, which never asks for a baseline. **Save every device of the network** is Save All, `Source: save_all`, and asks for a [baseline](baselines): it is earned when every device of the inventory was saved and recorded and each is at its committed intent, and denied otherwise, with the reasons. The decision is recorded even when no golden changed (a commit of its own, naming every device read), and an earned baseline is tagged then too: a network already in sync is the strongest evidence there is. A device whose golden already matched is "saved; its golden already matched".

## The result

The card leads with the count saved and recorded and whatever was not, its colour partial when any device was not. For the whole network it then says the baseline's outcome: "baseline earned" with its tag, or "No baseline" with each reason (a device not saved or not recorded, a device departing from its committed intent). Each outcome is a group, the ones to act on open: not recorded because the read-back did not match, not recorded because the running configuration could not be read, held, not answering, cannot be saved from here. **Retry the N not saved** opens Save for those devices, planned again. The commit is named, and History holds it.

## What Save does not do

- It changes no running configuration: each save carries the running configuration exactly as it is, including anything not in committed intent.
- It does not record without saving. A single device's [Capture](capture), on its own page, records a hand change before you decide.
- It rotates no credential, and writes no lab startup file.
- Nothing re-reads a device's startup configuration after the run until the hourly startup check runs.
