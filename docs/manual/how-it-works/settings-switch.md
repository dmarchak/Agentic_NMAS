# Inherit or stand alone: switch a network's settings

Every network either **inherits from Default** or is **standalone**. A network that inherits takes Default's value for any setting it does not set itself; a standalone network takes nothing from Default, so a setting it does not set is *not configured for this network*. Each group of settings (Grafana, Prometheus, Loki, Kea and the rest) also chooses for itself: **inherit from Default**, **its own**, or **not applicable**. The network's choice is only where a group starts until it chooses. Switching either is previewed, confirmed by you and recorded. Nothing is sent to any device.

![Switching a network's settings: the preview reads the network's settings and Default's and shows each group or setting today and after, a secret only as set; you confirm against the preview's fingerprint; the switch reads both again and refuses, naming what moved, if either changed; then it writes the network's own settings file and appends who, when and what changed to its settings record, which keeps any value removed. No device is contacted.](diagrams/settings-switch.svg)

You start it on the network's Settings page: **Make *network* standalone…** or **Change to inheriting from Default…** on the banner under the scope bar, and a group's three-way choice (or **Configure…**) on its card. The preview opens in place of the banner or the card; the confirm and the result happen there.

## The steps

1. `preview`: the network's settings and Default's are read, and what the switch changes is drawn. Read: the network's own settings file and Default's settings. Sent: nothing. Recorded: nothing. For the network's mode, each group that still follows the mode is listed today and after: becoming standalone names exactly the groups inherited today that become not configured ("Grafana, Loki and Kea are inherited from Default today; after this they are not configured"); inheriting again names what the network picks up. A group with a choice, values or a declaration of its own stays as it is, and the preview says so. For one group, each of its settings is drawn today and after with where the value comes from; a secret is drawn only as set or unset, and a URL carrying a credential is masked.
2. `confirm`: you confirm as a verified person. Read: nothing more. Sent: nothing. Recorded: nothing yet. The confirm carries the preview's fingerprint, which binds what the preview showed of today. *Its own* takes the group's values in the same card, starting from today's (a secret is never drawn back: an empty secret keeps the stored one, and an emptied field is not set here any more); *not applicable* takes a reason there.
3. `check_again`: the network's settings and Default's are read again and the plan is made again. Read: both, under the settings lock and the network's own lock. Sent: nothing. Recorded: nothing. If anything the preview showed has changed, nothing is saved and the refusal names each row as previewed and as it is now. Values you typed are checked against each setting's type here.
4. `write`: the network's own settings file is replaced whole. Read: nothing more. Sent: nothing. Recorded: the network's mode, the group's choice, its values (a secret encrypted) or its declaration of not applicable with who, when and why. The file is owner-only from creation. Default's settings are never written by a switch.
5. `record`: the switch is appended to the network's settings record. Read: nothing. Sent: nothing. Recorded: who, how that was established, when, from what to what, and every value removed or replaced, as it was stored (a secret still encrypted), so going back can restore it. The result says so if the record could not be written; the switch is made either way.

Readers and pages use the new settings at their next read: a standalone network's unconfigured group is not read at all, and its pages say "not configured" for it.

## Save a card {#save}

A card whose values are set here (each of Default's cards, and a network's group that is its own) takes its fields in place, with **Save** and **Test**. Default's values are what every network that inherits the group reads, and the card counts them.

1. `check`: what was sent is checked. Read: the group's settings as they stand. Sent: nothing. Recorded: nothing. A field that is not the card's own group is refused; a group the network inherits or declared not applicable is refused, naming its state, because its values are not saved there (making it the network's own is its switch, previewed above). An empty field keeps what is stored: a secret is never drawn back into the form, and a value holding a credential is not shown, so leaving either empty never wipes it. **Replace…** opens a set secret's field.
2. `write`: only the fields that changed are written. Read: nothing more. Sent: nothing. Recorded: Default's values in the installation's settings (a secret in the secrets store, encrypted), or a network's in its own settings file (owner-only, a secret encrypted). Each value is checked against its setting's type; a refusal names the setting.
3. `record`: the save is appended to the network's settings record. Read: nothing. Sent: nothing. Recorded: who, how that was established, when, the group and the names of the fields written, never their values. Saving what is already stored writes nothing and says "Nothing changed".

## Test a connection {#test}

**Test** asks the integration the card configures, with the values saved (save first: it tests what is stored, not what is typed). It changes no setting. The result is drawn in the card, passed or failed with what the service answered. The S3 archive's Test asks four things in order and names the first that fails: its bucket answers, a probe object is written, read back byte for byte, and its size stated. The probe is overwritten each time and never deleted, since Mercury's key cannot delete. The status bar and Needs attention ask the S3 archive only whether its bucket answers, and write nothing.

## Create a network {#create}

**New network…**, at the foot of the scope bar's network menu, opens in place of the page's tabs:
a name, a preview, then **Create**.

1. `check`: the name is checked as the folder it derives (`lists/<name in lower case>`). Read:
   the networks registered and the folders on this host. Sent: nothing. Recorded: nothing. A
   name another network has, a name whose folder another network uses ("Lab 3" and "Lab-3"
   share `lab_3`), or a folder that already exists with no network registered for it is
   refused, naming it: every page finds a network's records by that folder, so a second name
   for it would read another network's data.
2. `create`: the network is registered with an empty inventory on this host. It inherits every
   group of settings from Default; its Settings page offers the rest. Sent: nothing to any
   device or service.
3. `record`: who, how that was established, when and the name, in the installation's settings
   record.

## Delete a network {#delete}

**Delete this network…**, on a network's own Settings page (Network tab; never Default's, the
base layer), opens a preview: the devices, committed goldens and commits it holds, its remote if
it has one, and where its data goes. To delete it, type its name.

1. `check`: the preview is read again and compared. Read: the network's inventory, its
   repository and its remote record, and whether any of its devices is held or its drift run is
   in progress. Sent: nothing. A name typed differently, a preview out of date, or an operation
   running on the network refuses, naming it, and nothing changes.
2. `move`: its folder is moved to `lists_removed/<folder>-<UTC time>` beside the networks,
   inside its repository's lock. **Nothing is erased:** its goldens, intent, receipts and
   history survive there, and its remote, if it has one, keeps its copy.
3. `unregister`: the network leaves every page and every scheduled job. A person who had chosen
   it in the Network picker sees the installation's network instead.
4. `record`: who, how that was established, when and the name, in the installation's settings
   record. No device is contacted, and NetBox is not touched.

Renaming a network is not offered: every page finds a network's records by the folder its name
derives, so a rename must move the folder and every record that names the network (C639).

## What a switch does not do

- It contacts no device and changes no configuration.
- It never changes Default's settings, or another network's.
- Becoming standalone deletes nothing: values set here stay, and a group's own choice stands.
