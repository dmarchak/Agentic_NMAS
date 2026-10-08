# Retire a device

Retiring takes a device out of management completely, in one recorded act, keeping its
history. It is the only way a device leaves: deleting a row would leave it half-managed and
destroy the only stored copy of its credential. Retiring sends nothing to the device; it
changes the tool's own records, and NetBox's stored copy of the device's credentials where
the tool wrote them.

![Retiring: nothing is sent to the device; the tool masks NetBox's stored credentials first, clears the credential override, declares the lab startup file unmapped, commits the removal of the golden and intent (history keeps both), deletes the legacy file if it survives elsewhere, and deletes the inventory row last, only against a break-glass export holding the current credential.](diagrams/retire.svg)

## How you start it {#start}

On the device page, under Actions, **Retire…**: its card opens in place of the tab. You type
a reason, and the card plans again with it; the reason is part of the plan's hash, so the
confirm is bound to the reason you see. Confirming sends that hash back to be checked, and
the result is drawn in the same card. On the host, `nmas-retire --list <list> --device <device>
--reason "<why>"` prints the same plan and a hash; `nmas-retire ... --apply <hash> --actor
<you> --breakglass <file>` carries it out, reading the break-glass passphrase from the
terminal. Both run the same code.

## The preview

The preview reads and writes nothing, and contacts no device. It lists every step (done or
to do) and every refusal at once, each check drawn as a gate by name, and what retiring does
NOT do. It refuses when:

- **There is no reason.** It goes into the commit and the history.
- **The list's inventory is NetBox's.** Retire the device in NetBox instead.
- **The device is not in the list**, or is **pending onboarding** (use Abandon, which also
  reverses what onboarding created).
- **Uncommitted changes** under `host_vars/`, `golden/` or the manifest would ride into the
  retire commit, or the credential store cannot be checked.
- **NetBox cannot be read, or holds the device's credentials and cannot be masked.** NetBox
  is read over its REST API: the device of that exact name and its stored config context.
  If NetBox is configured and cannot be read, or its context cannot be checked, retiring is
  refused ("could not read" is not "nothing there"). If the context holds an unmasked
  credential and the tool's modification record shows the tool wrote that context, the
  credential is masked as the first step; if NetBox writes are off, retiring is refused,
  naming `nmas-netbox-mask-context` as the other way to mask it. If the tool did NOT write
  that context, it cannot mask it: retiring proceeds, says so, and a Needs attention row
  stays until someone removes it in NetBox.
- **The credential is not safe to drop.** Deleting the inventory row removes the only stored
  copy of the device's credential. The Device page reads the break-glass EXPORT LOG on the
  host: the newest export of this list must have recorded a digest of this device's current
  credential (an export taken before the last rotation does not count). Export one first
  from the [break-glass export](breakglass-export).
- **Another operation holds the device.**

The preview also reads, and states as read, what still watches the device after it leaves,
in two kinds (see [What watches it afterwards](#afterwards)): what is generated and so
dropped, and what survives with how it is removed. An advisory says when its golden carries
the `NMAS-HEARTBEAT` applet, which stays on the device: the tool cannot remove it.

## The apply

The plan is computed again; a different hash refuses with nothing done. Holding the device,
the steps run in this order, each skipped if already done, so a run that stops part way is
finished by running it again:

1. **Mask NetBox's stored credentials** (`netbox_mask`). Read: NetBox's device and its
   stored config context (REST API). Sent: nothing to the device; to NetBox, the context
   rewritten with the import's own masking. Recorded: the write in the tool's NetBox
   modification record, as you, with the plan's hash as its authority; then read back. Only
   when the preview made it a step. First, so a failed mask stops the retirement with
   nothing else done: once the device leaves, no import reaches it again.
2. **Clear the credential override** (`override`). Read: the credential store. Sent:
   nothing. Recorded: the device's override removed from the credential store, if it had
   one.
3. **Declare its lab startup file unmapped** (`declare`) (lab integration). Read: the
   settings. Sent: nothing. Recorded: a setting naming the device's startup file as
   deliberately unmapped, with the lab, your reason, you and the time. The lab's sync runs on
   the lab host and asks the tool over HTTP for its map of devices to startup files; once
   the device has left the manifest it is not in that map, so its startup file is no longer
   written, and the map's answer carries the declaration, which the sync's reconcile reports
   for the leftover file instead of a gap. Without a lab nothing reads it.
4. **One commit** (`commit`). Read: the repository. Sent: nothing. Recorded: `git rm` of the
   device's `host_vars/<device>.yml` and `golden/<device>.cfg`, its identity released from
   the manifest (NetBox kept, said), committed as you with `Retired-Device:`, `Reason:` and
   one `Not-Done:` trailer per thing deliberately kept. Only those paths are staged. Both
   files stay in history. The post-commit hooks then push the commit to the remote. A failed
   commit puts the tree back.
5. **The legacy file** (`legacy`). Read: the deprecated `golden_configs/` store and the
   repository. Sent: nothing. Recorded: the device's legacy file deleted, only when its
   content survives in the repository (the migration's verbatim backup or an equivalent
   committed golden), and the step says where. A file whose lines exist nowhere else is
   kept and named.
6. **The inventory row** (`row`). Read: the break-glass basis again. Sent: nothing.
   Recorded: the device's row deleted from the list's inventory. LAST, and only against a
   break-glass record holding this device's current credential, because the row is the
   only stored copy. Deleting it also tells the app's Prometheus target keeper the
   inventory changed, so the generated scrape files drop the device where the app writes
   them.

Nothing is sent to the device at any step.

## What retiring does not do

Each is correct, and each is named in the commit and on the screen so it is not mistaken
for an omission:

- The NetBox device is kept: NetBox records what exists, not what the tool manages. If the
  tool created it, Remove could still delete it, as a separate decision.
- A template approval is not withdrawn: an approval is of the template, never of its
  devices.
- What still watches it is said in two kinds, below.
- Its lab startup file freezes at its last sync (lab integration).
- Its running configuration is not changed, and its backups are kept.
- A session the app has pooled to it is closed by the app's idle reaper within two minutes,
  not by retiring.

## What watches it afterwards {#afterwards}

**Generated, so dropped.** The tool regenerates these from what retiring removes, so each
drops at its next regeneration, and the card says when:

- Prometheus's scrape targets, where the app writes them (a target directory is set): they
  are generated from the inventory, and a device with no committed golden is no target, so
  the retire commit drops it at the target keeper's next run. After the commit the result
  regenerates them and reads the files back, saying whether the device is gone from them.
  Where no target directory is set, the targets are not the tool's, and they are listed under
  what survives, with what Prometheus answered for the address.
- Its Grafana heartbeat rule: generated from committed intent, which leaves with the retire
  commit. The hourly check names it EXTRA until the heartbeat windows are re-measured and the
  rules installed without it (Monitoring, then its host step).

**What survives**, each with how it is removed:

- The NetBox device, its credential masked: delete it in NetBox if it is gone for good.
- A Grafana dashboard panel built by hand that names it: removed in Grafana by hand; the tool
  does not edit dashboards.
- A template's approval: it stays, because an approval is of the template.
- Its credential, only in the break-glass record. Managing it again is onboarding or adopt,
  not an undo.

**Its address afterwards.** The device has no device page once retired: its address shows
its retired record instead, read from the retire commit (who retired it, the reason, the
commit, when), with its history (the History page filtered to it) and a way to onboard it
again.

## Two ways in, two kinds of evidence

The Device page's Retire trusts the break-glass EXPORT LOG, because it cannot reach a file
on your laptop, and says so: the log records what an export wrote, and cannot show the file
still exists or that its passphrase is known. The command on the host (`nmas-retire`) opens
the record itself, with the passphrase you type, and refuses unless the record holds this
device's current username and password for this list.
