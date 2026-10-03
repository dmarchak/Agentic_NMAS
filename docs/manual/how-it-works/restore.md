# Restore and re-apply a baseline

A restore sends a device back toward an earlier recorded moment: one device's golden, or a
whole baseline across the devices you choose. It is a deploy whose target is the past
instead of intent, and it runs through the same pipeline. It changes each device's running
and startup configuration, its golden, and its committed intent, which moves back with it.

![A restore in three bands. In the tool, the stored golden and intent at the chosen moment are read through a reader that allows nothing else, and the program is the difference between that golden and today's committed golden; a person confirms it. The run reads the device, sends the program over SSH, reads it again and verifies against the moment's intent. One commit records the new goldens and puts the moment's intent back for each device that succeeded.](diagrams/restore.svg)

## The preview

You start a restore from one of four places: the device page's **Actions › Restore from…**,
which opens the restore in place of the tab, listing that device's restore points (pick one,
then **Preview** it); the Baselines panel's **Re-apply this baseline**, which asks for
a scope first (no device is ticked, and the whole fleet is a box of its own); **Restore Golden
Config**, on the Device page for that device or on today's device list for the ticked devices,
at their golden now (HEAD); or an
approved revert in the approval queue, which opens this preview for its device at HEAD. The
browser posts the moment (`ref`) and the devices to `/golden/restore/preview`, and the server
answers from git and the credential store. The preview opens no device session:

1. **Choose the moment and the scope.** Read: the device's golden now, its own
   `golden/<device>/<time>` tags, and every baseline that holds a golden for it, from git;
   for each point, the account lines its golden holds against those at HEAD. Sent: nothing.
   Recorded: nothing. Each point is marked current, refused, an account added back, or no
   golden, before you click; a withdrawn or deleted baseline is not offered.
2. **Build each target.** Read: the moment's golden and intent, through a reader that allows
   `golden/` and `host_vars/` and refuses anything else, and this list's inventory. Sent:
   nothing. Recorded: nothing. Templates, bindings and approvals are never read at the moment:
   they are code, and rolling them back to restore a network would revert template fixes.
   Each device left out is named with its reason: not in today's inventory; gone from NetBox
   for this list; no golden at the moment (for a whole baseline, a device the baseline
   predates, which is left exactly as it is and makes the baseline a partial restore point);
   no committed intent at the moment; or the moment's intent no longer reproduces its own
   golden through today's template, or names a secret the credential store does not hold.
3. **Ask about un-onboarding.** Read: nothing. Sent: nothing. Recorded: nothing. For a device
   that had no committed intent at the moment, its configuration cannot be re-applied while
   today's intent stays (the next plan would offer to undo the restore), so you are asked to
   leave it as it is (the default: nothing sent, nothing recorded) or to un-onboard it too
   (its configuration re-applied and its committed intent removed, in the same record). Choosing
   to un-onboard previews again with it, because a skipped device had no program to show.
4. **Authorise the lines that need a reason.** Read: the program's dangerous lines, and any
   line in a secret position the moment would add that the device does not hold (an old
   community, an account removed since). Sent: nothing. Recorded: nothing. Each such line asks
   for your stated reason beside it (on today's pages, a dialog before the program is drawn);
   the preview runs again with them, and the reasons go into the hash. An account added back is
   never typed past: it is a line with its reason, like a dangerous one, and an account the
   device holds is never changed.
5. **Compute the program.** Read: the moment's golden and the device's golden as committed at
   HEAD. Sent: nothing. Recorded: nothing. The program is what the moment had and today's
   golden lacks, each line under its section, built by the deploy's own builder; a running IP
   SLA operation the moment defines differently is deleted and defined again. It is ADDITIVE:
   lines are listed as `add` or `replace`, and residue (on the device, absent from the moment)
   is listed under its section and NOT removed. Blocks that cannot be re-applied at all
   (certificate chains, licence UDI, banners) are named.
6. **Check the gates.** Read: the program and today's golden. Sent: nothing. Recorded:
   nothing. Each gate is drawn by name: a golden at this moment; printable ASCII; credential
   unchanged (a line that would rewrite an account the device holds now refuses the device); no
   secret re-added (a credential or community the moment had and the device no longer holds
   waits for your reason, with its program shown); no other operation holds the device; and,
   at apply, the stored capture unchanged. A baseline older than a rotation would otherwise put
   back a password the rotation retired.
7. **State the intent half.** Read: the moment's intent and today's committed intent at HEAD.
   Sent: nothing. Recorded: nothing. Each device says whether its intent is unchanged, will be
   set back to the moment's by a forward commit, or will be removed (un-onboarding).

**The device itself is not compared.** The program is the difference between the moment's
golden and today's golden, never the device as it runs now. So restoring a device to its golden
now (HEAD) sends nothing by construction, and a device with nothing to send is still read and
its running configuration recorded as its golden (see [The run](#the-run)): a hand change on it is
recorded, not undone. To undo a hand change, capture the device first (see
[Capture and Save All](capture)), then restore from the point before the change; a line the
hand change added is residue, which only a [removal](removal) takes away.

## The run

On the device page, the confirm starts the restore as a job holding the device, in the list
the card was drawn in (never whichever list is active), and the card shows the pipeline's
stages as they run, then the result from the receipt. It answers at once, so a restore that
waits out BGP's hold time is never cut off by a proxy's time limit. From the Baselines panel,
you tick the devices and confirm. The browser posts the capture and command hashes it was
shown to `/golden/restore/apply`, which needs a verified person (the request's Cloudflare
Access assertion, from a trusted peer). Before anything else, any revert the old path queued in
the approval queue is rejected with a reason, because it carries whole-config text that path
pushed with none of these guards. Then, as for a deploy: the targets are built again, each
program and its hash recomputed and compared (a mismatch refuses that device, nothing sent),
the devices are held, and a device with nothing to send is read once over SSH and its
pipeline does not run.

Each other device runs the deploy's pipeline (see [Deploy a change](deploy#the-run-stage-by-stage)
for the commands each stage sends and reads):

1. `netbox_query`. Read: the device's NetBox record, only where NetBox is configured. Sent:
   nothing. Recorded: whether NetBox answered. Nothing it reads changes the program.
2. `template_render`. Read: the confirmed program. Sent: nothing. Recorded: nothing. No
   template is rendered at all: the target is the stored configuration.
3. `ci_gate`. Read: the program. Sent: nothing. Recorded: nothing. Each dangerous line must
   carry your authorisation and reason; a secret line re-added is checked by the target's own
   gate, which runs on every path.
4. `pre_snapshot`. Read: over SSH, the neighbour tables, interfaces, routes and running
   configuration. Sent: nothing. Recorded: the pre-change snapshot, for a rollback.
5. `config_diff`. Read: the program and the running configuration. Sent: nothing. Recorded:
   the counts. Refuses a program the device holds in full, or one adding more than 200 lines.
6. `deploy`. Sent: the program in configuration mode over SSH, then `write memory`. Recorded:
   the push time.
7. `post_snapshot`. Read: the same facts on a new SSH session. Sent: nothing. Recorded:
   nothing yet.
8. `verify`. Read: the snapshots, and the device again in the settle windows. Sent: nothing.
   Recorded: the result, for the receipt. It checks what the MOMENT's intent declares, so a
   protocol the restore was meant to bring back is checked, not assumed; for a moment that
   predates the device's intent, only what was running before is checked. A failure rolls the
   device back exactly as a deploy does (see
   [When verify fails](deploy#when-verify-fails-the-rollback)).
9. `save_golden`. Read: the post-change running configuration. Sent: nothing. Recorded: the
   capture, staged and handed to the batch.
10. `audit_log`. Recorded: the run's audit entry, as for a deploy (the latest per device).

Then, once for the batch:

- **One commit.** Recorded: the new goldens of the devices that succeeded, with
  `Source: restore` and `Actor:` you, and, in the SAME commit, the moment's committed intent
  written back verbatim for each of those devices (`Restored-Intent:`), or removed where you
  chose to un-onboard (`Un-Onboarded:`). Until the commit, that intent is staged in
  `.nsot/staging/restored_intent/`. A device whose restore failed keeps today's intent, because
  device and intent move as one unit, so the next deploy does not offer to undo the restore.
- **Publish**, as for a deploy: pushed to the remote where one is set.
- **Ask Oxidized to fetch (lab integration)**, where Oxidized is configured.
- **Receipts**, one row per device, with the action `restore` and the moment named; an approval
  item that handed off to this restore is closed only for devices that succeeded.

## The baseline the restore earns

A restore earns a new baseline only if EVERY device in the network is measured equivalent to
the chosen moment afterwards, however it got there: pushed, already matching (read once for
that reason), or needing one line. A device not measured, one that failed, or one still
differing denies it. Residue denies it: a merge cannot remove a line, so the network is not at
that moment while residue remains. As for every baseline, each capture must also match its
committed intent, and the decision is recorded in the commit's `Baseline:` trailer.

## A withdrawn baseline

A baseline someone withdrew (it recorded a broken state) is refused wherever it is read: the
preview and the apply answer with the reason it was withdrawn and send nothing, and the
Device page's chooser does not offer it. The withdrawal is recorded with who decided it and
why.

## What a restore does not do {#what-a-restore-does-not-do}

- It removes nothing: residue stays. Removal is chosen on a deploy, line by line (Mode B).
- It does not read the device to compute the program, so it does not undo a change made on the
  device since its last capture.
- It never rolls back templates, bindings or approvals, and never rewrites an account's
  credential.
- It does not re-apply certificate chains, licence UDI or banners.
