# Mark a device drained

A drained device is out of service on purpose: its traffic moved off it for a patch, a reload or a cable move. Marking it drained tells everyone looking that the quiet is intended. The mark is a person's word with a reason, recorded with who and when; it sends nothing to the device. Moving the traffic is a change to the device's intent, deployed on its own (Plan a deploy).

![Marking a device drained, or clearing the mark: you give a reason; the tool checks you are a verified person, that the reason has the shape of one and that the device is not already in that state, then appends who, when and why to the network's drained record. The badge, History and Needs attention read that record. Nothing is sent.](diagrams/drained.svg)

## Set or clear it

On the device's page, open Actions > Mark drained… The card says the device's state now, what the mark does, and asks for a reason. Mark drained records it. While the device is drained, the same row reads Clear the drained mark…, and its card asks for a reason the device is back.

## The steps

1. **Check** (`check`). Read: the network's drained record, under its lock. Sent: nothing. Recorded: nothing. Refused, naming why, with nothing recorded: no verified person on the request, a reason that is not the shape of one (the same rule as an authorisation's reason), a device already drained, or a mark to clear on a device that is not drained.
2. **Record** (`record`). Read: nothing. Sent: nothing. Recorded: one line appended to `drained.jsonl` in the network's data folder (owner-only), with the device, drained or cleared, your reason (masked), you, how you were verified, and the time. A device's state is its newest line. Nothing is ever rewritten or removed.

## What the mark changes

- **The Devices list and the device page** draw a Drained badge beside the device's name; its hover says who drained it, when and why. Both redraw when the mark is set or cleared anywhere.
- **History** shows each mark and each clear on the device's timeline ("Marked drained", "Drained mark cleared"), with who and the reason; filter by Drained and back.
- **Needs attention** does not raise a Grafana alert whose every device is drained: its traffic falling is the drain. The Grafana alerts source says, under What was checked, how many alerts it held back, on which devices, and whose drain. An alert that also names a device in service is raised as usual, and so is an alert that names no device or every device's heartbeat at once.

## What it does not do

- It sends nothing to the device and changes no intent, golden or NetBox record.
- It does not move traffic: draining the traffic is a deploy, and restoring it is another.
- It does not declare a planned restart: a reload while drained still declares its own window.
- It does not clear itself: a drained device stays drained until a person clears the mark.
