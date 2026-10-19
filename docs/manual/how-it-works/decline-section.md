# Decline a monitoring section on one device

Coverage shows what each device is not configured for. Some gaps are a person's choice: edge1's
IP SLA, for example, would probe core1, which carries the management path, so the operator
chooses not to probe it. **Decline…**, beside **Add to intent…** on a gap's row (and on the IP SLA
page), records that choice with a reason, as you, in the device's committed intent. From then
on the gap reads **Declined**, with who, when and why, on Coverage and on the IP SLA page, and
the summary counts it as declined, never as covered or missing. **Undo decline…** takes it
back.

![Declining a monitoring section on one device, with a reason (C718). The preview is the intent change: one profile_exclude entry with the section, your reason, you and the time. You confirm its hash; at apply the device is held, the change computed again and refused if it moved, and exactly that device's intent file is committed as you. Coverage and the IP SLA page then read it as declined, never as a gap. Nothing is sent; Undo decline is the same with the entry removed.](diagrams/decline-section.svg)

## What it records

One entry in the device's `profile_exclude` list, the list the monitoring profile already
reads: the section, your reason, who declined it and when. It is not a second list of declines:
the profile leaves a declined section out of what it supplies, no deploy of the profile sends
it, and the IP
SLA page suggests no probe for a device whose IP SLA is declined. An entry written by hand
without a name and a time still reads as excluded, with its reason.

A declined IP SLA with probes already in the device's intent is refused, naming them: remove
the probes first, so intent never says both "probe this" and "do not". A device with no
committed intent is refused, and so is a section that is not one of the monitoring profile's,
a decline of a section already declined (naming its reason), and an undo of a section that
is not declined.

## The steps

1. `preview`: the intent change, shown as the lines of `host_vars/<device>.yml` it adds (or
   removes, to undo), with a decline's checks: you are a verified person, and your reason has
   three words or more. An undo carries the decline's own reason, so its preview shows neither check;
   confirming it still needs a verified person.
   Typing the reason asks again; nothing is written.
2. `hold`: the device is held, so no other operation changes its intent meanwhile.
3. `recompute`: the change is computed again and its hash compared with the preview's. If the
   device's intent moved, or another person confirms what you previewed, nothing is committed
   and the card says what moved.
4. `write`: the device's intent file is written.
5. `record`: one commit as you, `Source: decline`, with a `Section: <section>` line; a
   commit that fails puts the file back.

## What it does not do

It sends nothing to the device: its configuration does not change, so there is no program, no
session and no verify. It does not remove anything already configured on the device. Undo
decline… is a second commit, as you; the decline's commit stays in History.
