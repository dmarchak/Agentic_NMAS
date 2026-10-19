# Capture and Save All

A capture moves the golden toward the device: it reads what each device runs now and records
it as that device's golden. Save All is the same record across every device in the network,
and it is the one that can earn a baseline; on the new pages it is **Devices > Save** for every
device of the network ([Save](save)), which also saves each device's startup first. A capture
changes nothing on a device: it reads, and it writes one commit in the list's repository.

![A capture in two bands. In the tool, a person starts the preview; each device is read over its own SSH session, at once, and each read is judged, then compared with the device's golden and its committed intent. After the person confirms, every device is read again and one commit records the goldens, with a baseline tag only when the whole fleet matches its intent. Nothing is sent to any device.](diagrams/capture.svg)

## The preview

You start a capture from the device page's **Actions > Capture** (that device, its card drawn
in place of the tab). The same card is opened by a drift row's **Capture <device>…** on Needs
attention, by **Capture** under Keep it in the Overview tab's drift detail, and by
**Capture <device>…** beside a device the template editor's check could not validate for want
of a golden. The card posts its device to `/v2/device/<name>/capture/start`, which
starts the job, and its confirm reaches the apply through `/v2/device/<name>/capture/confirm`.
Every device of a network at once is Devices › Save (see [Save](save)), which reads and
records each device the same way; the devices with no committed golden are one of its scopes,
**Actions › Save the devices of <network> with no golden…** (see [Save](save#no-golden)),
which saves each one to startup as well as recording it.

1. **Start the job.** Read: this list's inventory. Sent: nothing. Recorded: a job in the server's memory (a restart loses
   it, and asking for it then says so). The request answers at once with the job's id, so no
   request waits on a device: a fleet read one device after another took longer than the
   100 s the edge allows a request.
2. **Read every chosen device now.** Read: on a fresh SSH session per device, opened with the
   credential its inventory row holds, `enable` and then `show running-config`, sent once,
   waited for up to `nsot_config_read_timeout`, never sent again on that session; the session
   is closed after the read. Up to 16 devices are read at once, so a fleet read takes about as
   long as its slowest device. Sent: nothing beyond the read. Recorded: progress for the
   in-flight panel ("read 3 of 9 device(s); waiting on …"), and each device's connect and read
   times in the app log. When the job ends it announces over the page's live channel and the
   page fetches the preview by its id. The card has no Check now control: if the channel is
   down, the page's live note says live updates stopped, and the card fetches the preview
   once the channel reconnects.
3. **Judge each read.** Read: the read and the device's committed golden. Sent: nothing.
   Recorded: nothing. A configuration that came back stitched together (two `end` lines or
   none, not ending with `end`, a device prompt, an echoed command, two `hostname` lines,
   another device's hostname, or more than 1.6 times the size of its last golden) is refused
   with "the device's output could not be read reliably", and nothing will be recorded for it.
4. **Compare each capture twice.** Read: the committed golden, and committed intent rendered
   through the device's bound template with the monitoring profile merged and secrets in
   memory. Sent: nothing. Recorded: nothing.
   - Against the golden: what would change in the record. A regenerated self-signed
     certificate is labelled as one line, not drawn as hex.
   - Against committed intent: whether the device is at intent, or departs from it, line by
     line.
   - The structure: a capture with fewer of some section (interfaces, terminal lines) than its
     golden needs your reason, unless committed intent renders the smaller structure.
5. **No baseline from one device.** Read: nothing more. Sent: nothing. Recorded: nothing.
   The card says so: "No baseline is taken: one device is not the fleet". A baseline is
   earned only by Devices › Save when it saves every device of the network together, and
   only when every device was read and every one matches its committed intent (see
   [Save](save)). A one-device capture that changes nothing cannot be confirmed: the card
   says there is nothing to confirm.

## The confirm and the apply

On the device page's card, **Record <device>'s golden** posts that one device's capture hash,
as the preview showed it, and its list, and stays busy on itself until the result replaces the
card. A structure that
shrank without committed intent explaining it needs your reason: the card names that check
and asks for the reason beside its confirm, which carries it. A reason that is not the shape
of one (a few words, not a copy of the change) is refused before anything is read; with none,
the save refuses the device and records nothing. The reason is recorded on the commit's
`Structural-Change:` line as yours, and the result says so. The apply needs a verified person
(the request's Cloudflare Access assertion, from a trusted peer), who is the actor recorded
below.

1. **Hold the devices.** Read: the device lock. Sent: nothing. Recorded: a lock per device
   until the commit is made. A device another operation holds is refused alone, by name,
   because a capture taken while a deploy or restore changes it would record a half-made
   state.
2. **Read each device again.** Read: `show running-config` on a fresh SSH session per device,
   at once, judged as in the preview. Sent: nothing. Recorded: nothing. A device whose capture
   hash moved since the preview is refused alone, naming both hashes; a device that cannot be
   read is refused alone with its reason. Nothing is recorded for either.
3. **One commit.** Read: the reads just taken. Sent: nothing. Recorded: one commit in the
   list's repository, as you, with `Source: capture` (or `save_all` for the fleet), an
   `Intent-Match:` trailer saying whether each device matched its intent, any reason you gave
   for a smaller structure, and a `golden/<device>/<time>` tag per changed golden. Each golden
   is checked again as it is written; a device that fails is left out of the commit and named
   with its own reason, never another device's.
4. **Decide the baseline.** Recorded: for a whole-fleet save, a `Baseline:` trailer. Every
   inventory device read and recorded (or unchanged), and every one at its committed intent,
   earns `Baseline: earned` and the tag `baseline/<time>`; anything less records
   `Baseline: denied:` with the reasons. When no golden changed, the decision is still
   recorded, as an empty commit, so a denial is never only a message on a screen.
5. **Publish.** Sent: the commit to the list's remote by `git push` where a remote is set,
   and each changed golden, masked, to the S3 archive where one is configured. Recorded: the push's outcome. The
   post-commit hooks run in the background and never hold the commit.
6. **Close what the capture answers.** Recorded: for every device recorded or found
   unchanged, each pending drift item is withdrawn, naming the commit, and the last drift
   check's rows for it are answered. Then the device locks are
   released, and the result is drawn from the outcome of each device. The commit is the
   record: the History page and the device page's History tab read it back.

## What a capture does not do {#what-a-capture-does-not-do}

- It sends nothing to a device: no configuration mode, no `write memory`. Saving the running
  configuration to the device's startup is [Persist](persist).
- It does not change intent. A device that departs from intent is recorded as it is, marked
  `Intent-Match: no`, and cannot be part of a baseline; deciding which side is right is yours.
- It does not compare the startup configuration, only what the device runs now.

## Why it works this way

The golden is a record of the device, so it is read from the device, never derived. And a
baseline claims the whole network was at its intent at that moment, so it is measured, never
granted because a save happened.
