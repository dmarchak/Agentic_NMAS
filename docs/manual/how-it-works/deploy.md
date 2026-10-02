# Deploy a change

A deploy moves a device toward its committed intent: it sends the lines intent has and the
device lacks, checks the device is still working, and records what landed. It changes the
device's running configuration and its startup configuration (the push ends with a save),
its golden in the list's repository, and the deploy record.

![The deploy in three bands. In the tool, the plan reads the committed golden and committed intent and builds the exact program, which a person confirms; the run then reads the device, sends the program over SSH, reads the device again on a new session and verifies; the batch commits one golden and writes a receipt per device. A failed verify sends an undo program back to the device.](diagrams/deploy.svg)

## Before the deploy: the plan

You change intent and commit it (editing is on today's Device page; the v2 Intent tab is
read-only). Then you open the plan from one of three places: the **Deploy plan** button on a
device's row in today's device list; the v2 Devices list's selection bar, **Plan a deploy…**,
which opens today's page with the ticked devices; or Monitoring > Coverage's **Apply**, which
plans only the monitoring profile's lines (see
[Monitoring templates](monitoring-templates)). The browser posts the device names to
`/deploy/plan`, and the server answers from git and the credential store. Planning opens no
device session:

1. **Read the committed golden.** Read: the device's golden as committed at HEAD in the list's
   repository (never the working file), and the device's row in this list's inventory for its
   platform. Sent: nothing. Recorded: nothing. The golden is the capture the program is
   computed against; a golden nothing committed, or one committed without a `Source:`
   trailer, refuses the plan by name.
2. **Render intent.** Read: committed intent (`host_vars/<device>.yml` at HEAD), the network's
   monitoring profile (merged in, the device's own value winning), the template the device is
   bound to in the network's library and that template's approval record, and the secrets
   intent names, from the credential store into memory only. Sent: nothing. Recorded: nothing.
   A device with no committed intent, or only onboarding's bootstrap intent, is refused here,
   because rendering its status quo as its goal would plan nothing and report success; a
   render still holding a mask, or one that would rewrite an account the device holds, is
   refused too.
3. **Compute the program.** Read: the render and the golden. Sent: nothing. Recorded: nothing.
   The program is each line the render has and the golden lacks, preceded by its full section
   chain (`interface …`, `router ospf …`), one `exit` per open level, never `end`; then any
   running IP SLA operation intent changes, deleted and defined again (the device refuses to
   edit a running one), refused naming the probe on a platform where that delete has not been
   measured; then any removals you selected ([Mode B](removal)), last. This exact list, byte
   for byte, is what will be sent.
4. **Attribute every line.** Read: the previous committed intent, rendered against the same
   golden, and the device's own intent rendered without the profile. Sent: nothing. Recorded:
   nothing. Each line is labelled from your edit, already pending before it (something on the
   device drifted since the last capture, or an earlier edit was never deployed), or from the
   monitoring profile, because merge-only sends every missing line and you should see what
   rides along.
5. **Check the gates.** Read: the template's approval, the render's report, the receipts (how
   often each flagged line was authorised on this device before), the rolled-back record and
   the device lock. Sent: nothing. Recorded: nothing. Each gate is drawn by name: template
   approved; committed intent; the template reproduces the device; every line modelled or
   acknowledged; printable ASCII; dangerous lines (`shutdown`, `no ip address`,
   `no router ospf|bgp|eigrp|isis`, `reload`, `erase nvram`, `crypto key zeroize`), each
   authorised by its exact text with your reason; blocked change (the program does not re-send
   a change that was rolled back); and no other operation holds the device. Two more are
   checked at apply: the stored capture is unchanged, and no credential changes.

To authorise a dangerous line you tick its box and type a reason (at least three words, not a
copy of the line); the device is planned again so its hash covers the reason. The confirm is
bound to a hash of the program and its authorisations. The apply recomputes it, and if the
stored golden, the intent or the template moved before you confirm, it refuses that device
with nothing sent, saying which side moved. **The device itself is not compared**: the program
is computed against the stored golden, so a change made on the device since its last capture
is not detected before the push. Capture the device first (see
[Capture and Save All](capture)).

## Confirm and apply {#confirm-and-apply}

You tick each device to deploy and press **Deploy confirmed devices**. The browser posts the
hashes it was shown, from the plan it drew (never fetched again), to `/deploy/apply`. The apply
needs a verified person: the request's Cloudflare Access assertion, checked, from a trusted
peer. That person is the actor recorded everywhere below.

1. **Recompute and compare.** Read: each device's committed golden, intent, profile and
   template again. Sent: nothing. Recorded: nothing. The program is rebuilt and its hash
   compared with the confirmed one, and the stored golden's hash with the confirmed capture
   hash; a mismatch refuses that device alone, naming both hashes.
2. **Hold the devices.** Read: the device lock. Sent: nothing. Recorded: a lock per device
   (a file lock the kernel releases if the holder dies), held until the receipts are written. A
   device another operation holds is refused by name, never queued.
3. **Prepare each device.** Read: the render again, with real secrets in memory. Sent:
   nothing. Recorded: nothing. The mask and credential checks run again, every selected removal
   must carry a reason of the right shape, and every addition must be a line of the render
   (merge-only). A device with nothing to send is read once over SSH (`show running-config`)
   so it counts as measured, and its pipeline does not run.

## The run, stage by stage

Each device with something to send runs one pipeline, on its own SSH session pool, closed when
the run ends. Its stages, in the order the code declares them:

1. `netbox_query`. Read: the device's NetBox record and interfaces over NetBox's API, only
   when NetBox's URL and token are set. Sent: nothing. Recorded: whether NetBox was available,
   in the audit entry. On this path nothing it reads changes the program, and a NetBox that
   does not answer never stops a deploy.
2. `template_render`. Read: the confirmed program. Sent: nothing. Recorded: nothing. Nothing
   is rendered again: the confirmed list is the only thing that may be sent, and an attempt to
   replace it raises.
3. `ci_gate`. Read: the program. Sent: nothing, and no session is open yet. Recorded: nothing.
   Every line matching a dangerous pattern must be authorised by its exact text with a reason
   of the right shape; this local check runs on every path, whether or not a hash was compared.
4. `pre_snapshot`. Read: the first SSH session, to the device's management address with the
   credential its inventory row holds: the neighbour tables of every routing protocol the
   device answers for (`show bgp all summary`, `show ip ospf neighbor`,
   `show ospfv3 neighbor`, `show ip protocols` for RIP and others), the interface states,
   `show ip route summary`, and `show running-config`. Sent: nothing. Recorded: the running
   configuration as the pre-change snapshot, for a rollback. A device that cannot be read
   reliably here is refused with nothing sent. If the running configuration alone cannot be
   read, the run continues without it, and a rollback then has nothing to build from. Known
   gap: the snapshot is read through, and stored in the `pre_change/` folder of, the list the
   server has selected, not the list the deploy carries.
5. `config_diff`. Read: the program and the pre-change running configuration. Sent: nothing.
   Recorded: the counts, in the audit entry. It compares each program line's text with the
   running configuration's lines (by text, not by section) and refuses a program whose every
   line is already present, or one adding more than 200 lines. With no running configuration
   it is skipped.
6. `deploy`. Read: the device's replies. Sent: `enable`, then the program in configuration
   mode on the pooled SSH session, then `write memory`. A reply line such as `% Invalid input`
   or `ERROR:` stops the push. NETCONF is used instead only where the platform map and the
   `netconf_enabled` setting both allow it, falling back to SSH on a NETCONF error. Recorded:
   the time the push ended, for the BGP watch. Nothing is negated except a re-created IP SLA
   operation's delete and a removal you chose.
7. `post_snapshot`. Read: the push's session is closed and a NEW one opened; the same facts as
   `pre_snapshot`, and `show running-config`. Sent: nothing. Recorded: nothing yet; verify and
   `save_golden` use it.
8. `verify`. Read: the two snapshots, and the device again while it waits. Sent: nothing.
   Recorded: what it compared, for the receipt. A neighbour lost, in any protocol read before
   the push, is waited out for its settle window (by default OSPF 45 s, BGP 60 s, RIP 90 s, others 45 s)
   and fails only if it persists; a count still rising is reported as not yet converged. The
   route table must keep 90% of its routes, re-read for up to 90 s; the count of interfaces up
   must not fall; BGP is read once more no earlier than its configured hold time after the push
   (180 s when none is set), except for a program that touches only management sections
   (terminal lines, logging, SNMP, NTP, banners, users), where each new line is read back from
   the configuration instead. Removals must read back gone, and re-created IP SLA operations as
   intent defines them. A failure triggers a rollback. A protocol intent declares that the
   device was not running before and is still not up, a read that could not be trusted, or a
   new line not read back makes verify not pass, without a rollback: undoing the change cannot
   fix those.
9. `save_golden`. Read: `post_snapshot`'s running configuration. Sent: nothing. Recorded: the
   capture, staged in `.nsot/staging/post_deploy/` and handed to the batch, which commits once
   for every device (see [What is recorded](#what-is-recorded)). It runs when verify did not
   fail, including when verify did not pass, and records nothing for a device rolled back or
   with no post-change read.
10. `audit_log`. Read: the run's results. Sent: nothing. Recorded: a JSON entry,
    `pipeline_audit/tpl-<device>.json` in the data directory: stages, push results, the
    snapshot counts, verify and whether a rollback ran, without the program. It is written
    whatever happened, and the next deploy to that device overwrites it; the receipt is the
    durable record.

## When verify fails: the rollback

A failure in `deploy`, `post_snapshot` or `verify` starts the rollback on a device where a push
was attempted, including one whose push failed half-way:

1. **Read what landed.** Read: `show running-config` on a fresh SSH session, compared with the
   pre-change snapshot. Sent: nothing. Recorded: the lines that landed and the lines lost, in
   the result. On a partial push what landed differs from what was sent, and only what landed
   is undone; a line the device rejected is reported as never applied.
2. **Build the undo.** Read: the pushed program, the snapshot and what landed. Sent: nothing.
   Recorded: nothing. An old line is sent back where the change replaced it, a new line is
   negated where there was none, a section the push created is removed by one negation, a
   removed line is put back verbatim, and a re-created IP SLA operation gets its old
   definition back. Every undo line must answer something the push sent, and the undo is
   exempt from the dangerous-line gate, since undoing `no shutdown` is `shutdown`.
3. **Send it.** Sent: the undo in configuration mode on the pooled session, then
   `write memory`. Recorded: nothing yet.
4. **Read it back.** Read: `show running-config` on a fresh session; the undo is computed again
   against it. Sent: nothing. Recorded: the outcome, by name: restored, nothing to undo,
   incomplete (with what remains), sent but unverified, failed, or not attempted (no
   pre-change snapshot).
5. **Block the change.** Recorded: the device's current intent commit and the failed additions,
   in `.nsot/rolled_back.json` in the list's repository. The next plan refuses while those
   lines would be sent again, until you revert the intent or lift the block with a reason.

## What is recorded

After the last device, in this order:

1. **One golden commit for the batch.** Read: the captures the devices handed back, and the
   inventory. Sent: nothing. Recorded: one commit in the list's repository naming the devices
   that succeeded, with `Source: pipeline`, `Actor:` you, `Actor-Verified: access`, a
   `Program-Hash:` per device, `Failed-Devices:`, `Intent-Match:` and the `Baseline:` decision,
   and a `golden/<device>/<time>` tag per changed device. It is tagged `baseline/<time>` only if
   every inventory device was targeted and succeeded and every capture matches its committed
   intent. When no device succeeded, nothing is committed.
2. **Publish.** Sent: the commit to the list's remote, by `git push` where a remote is set, and
   to the S3 archive where one is configured. Recorded: the push's outcome, which the Remote
   card and Needs attention read. The post-commit hooks run in the background and never hold
   the commit; they also regenerate the Prometheus scrape targets from the changed goldens.
3. **Ask Oxidized to fetch (lab integration).** Sent: where Oxidized is configured, an HTTP
   request asking it to fetch each changed device now. Recorded: the request, per device. It
   asks and never waits.
4. **Write the receipts.** Recorded: one masked row per device, sent, failed or refused, in
   `deploy_receipts.jsonl` in the list's data folder: the program, its hash against the
   confirmed one, you, each authorisation's reason, the checks verify ran, the rollback and the
   commit. The result on screen is drawn from these rows, and the device page's History tab
   reads them back. Then the device locks are released.

## Many devices at once

A batch deploys one device after another (`deploy_max_workers`, default 1), in the order the
confirm lists them: on today's wizard, the order of the plan; on Monitoring > Coverage's Apply,
the order you set with Earlier and Later. A device refused at apply is skipped and the rest
proceed. After `deploy_verify_failure_limit` verify failures (default 2) the circuit breaker
trips and the remaining devices are not attempted, each saying so. Sequential on purpose: a bad
change stops after the first devices it breaks, instead of reaching the whole fleet at once.
Today's wizard waits for the whole batch in one request, with the in-flight panel showing what
runs; the v2 Apply runs as a job, answering at once and drawing each device's start and finish
as it happens.

## What a deploy does not do {#what-a-deploy-does-not-do}

- It does not read the device to compute the program: the stored golden is the baseline, and a
  hand change since the last capture is neither detected nor undone.
- It removes nothing you did not tick, and never changes an existing account's credential.
- It does not re-render at apply: what you confirmed is what is sent.
- It does not roll back for a protocol that was not running before, or for a read it could not
  trust: it says verify did not pass and leaves the change in place.
