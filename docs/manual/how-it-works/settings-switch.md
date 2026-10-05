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

## What a switch does not do

- It contacts no device and changes no configuration.
- It never changes Default's settings, or another network's.
- Becoming standalone deletes nothing: values set here stay, and a group's own choice stands.
