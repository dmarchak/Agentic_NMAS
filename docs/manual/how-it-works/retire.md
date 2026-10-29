# Retire a device

Retiring takes a device out of management completely, in one recorded act, keeping its
history. It is the only way a device leaves: deleting a row would leave it half-managed and
destroy the only stored copy of its credential. It also frees the device's name: a new device
given the same name later inherits nothing of the old one (no restore point, receipt, block,
queued item, policy, template, map place, heartbeat or telemetry rule, reservation, console
survey or NetBox record).
Retiring sends nothing to the device; it changes the tool's own records, Kea's reservations
and NetBox's record of the device.

![Retiring: nothing is sent to the device; the tool masks NetBox's stored credentials first, clears the credential overrides and the staged credential, removes the device's Kea reservations, commits the removal of the golden, intent and template override (history keeps them), archives its golden tags and rollback block, withdraws its queued items, rotation-policy memberships, Topology entries and heartbeat rule, sets its NetBox record to Decommissioning and renames it, deletes the legacy file if it survives elsewhere, forgets the SSH host key it kept for the device's address, and deletes the inventory row last, only against a break-glass export holding the current credential.](diagrams/retire.svg)

## How you start it {#start}

On the device page, under Actions, **Retire…**: its card opens in place of the tab. You type
a reason, and the card plans again with it; the reason is part of the plan's hash, so the
confirm is bound to the reason you see. Confirming (**Retire <device>**, which needs a
verified person) sends that hash back to be checked, and the result is drawn in the same
card; once the device is retired the card says it has no device page now and offers
**Back to Devices**. On the host, `nmas-retire --list <list> --device <device>
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
- **Uncommitted changes** under `host_vars/`, `golden/`, the manifest or (when the device has
  a template override) `templates/bindings.yml` would ride into the retire commit, or the
  credential store or the template bindings cannot be read.
- **NetBox cannot be read, or holds the device's credentials and cannot be masked.** NetBox
  is read over its REST API: the device of that exact name and its stored config context.
  If NetBox is configured and cannot be read, or its context cannot be checked, retiring is
  refused ("could not read" is not "nothing there"). If the context holds an unmasked
  credential and the tool's modification record shows the tool wrote that context, the
  credential is masked as the first step; if NetBox writes are off, retiring is refused,
  naming `nmas-netbox-mask-context` as the other way to mask it. If the tool did NOT write
  that context, it cannot mask it: retiring proceeds, says so, and a Needs attention row
  stays until someone removes it in NetBox.
- **A staged credential is not the inventory row's.** A rotation or an adoption that was
  interrupted leaves the new password staged; when it differs from the row's it may be the
  only copy of what the device accepts now. Settle it first (`nmas-rotation-recover`, or
  `nmas-adopt-recover` for an adoption), then retire.
- **A store the steps change cannot be read**: Kea's reservations (ZTP's fragment, or a DHCP
  reservation Kea refuses to plan the removal of), the golden tags, the record of rolled-back
  changes, the approval queue, the Topology declarations or layout, Mercury's NetBox
  created-object record, or another network's inventory (asked when a rotation policy names
  the device). Each is "could not read", never "nothing there".
- **The credential is not safe to drop.** Deleting the inventory row removes the only stored
  copy of the device's credential. The Device page reads the break-glass EXPORT LOG on the
  host: the newest export of this list must have recorded a digest of this device's current
  credential (an export taken before the last rotation does not count). Export one first
  from the [break-glass export](breakglass-export).
- **The SSH host key record, or any network's inventory, cannot be read.** Retiring forgets
  the key the tool kept for the device's address unless another device has that address,
  and "could not read" is not "no other device".
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
2. **Clear the credential overrides** (`override`). Read: the credential store. Sent:
   nothing. Recorded: the device's override removed from the credential store at every
   address it was known by: its row's, its manifest's and the address ZTP reserved for it.
   An override at a reserved address another device now has is that device's: KEPT, and
   said.
3. **The staged credential** (`staged`). Read: the device's staged password
   (`.nsot/staging/credential/<device>.enc`) and an adoption's sidecar. Sent: nothing.
   Recorded: both deleted, as abandon deletes them, only when the staged password is the
   inventory row's (which the break-glass export holds); compared in memory, never shown.
4. **Kea's reservations** (`reservations`). Read: ZTP's fragment (by the device's recorded
   MAC or its name) and the DHCP page's subnet files (by its name or any address it was known
   by, IPv4 or IPv6). Sent: nothing to the device; to Kea, each removal through its own
   writer: ZTP's reservation through ZTP's writer, the one abandon uses, and a DHCP
   reservation through the DHCP page's own removal, planned in the preview and confirmed by
   its hash. Recorded: `dhcp/ztp-reservations.yml` or `dhcp/reservations.yml` committed in
   the Kea owner's repository as you, so each reservation stays in that record's history.
   Before the commit, so an address is never left reserved for a device nobody knows.
   **Then its Kea leases** (`leases`). Read: every lease Kea holds, either family, for the
   device's recorded MAC or any address it was known by. Sent: nothing to the device; to Kea,
   `lease4-del` or `lease6-del` for each, through [the one release](dhcp-lease-release), read
   back. Recorded: `dhcp/released-leases.yml` in the Kea owner's repository as you. A lease
   outlives its reservation and refuses the address to the next device that asks with another
   client identifier, so it goes too; one Kea now holds for another client is left, and said.
   **Then its link's ZTP subnet** (`ztp_subnet`). Read: Mercury's IPv4 subnet file, for a
   relayed ZTP subnet whose record says this device's Add device added it for its link (C1460),
   with the reservations and leases still in it. Sent: nothing to the device; to Kea, the
   subnet's removal through [the subnet writer](dhcp-subnet) (its own hash, `-t` on the
   candidate, a reload, a read-back). Recorded: `dhcp/subnets.yml` in the Kea owner's
   repository as you. Only when nothing else is in it once this device's reservation and lease
   are gone; a subnet a person added, or one still serving another device, stays, and is said.
   The parent's relay stays in its intent and the link's NetBox prefix stays: a device added
   there again gets the subnet again.
5. **One commit** (`commit`). Read: the repository. Sent: nothing. Recorded: `git rm` of the
   device's `host_vars/<device>.yml` and `golden/<device>.cfg`, its own template override
   taken out of `templates/bindings.yml`, its identity released from the manifest (NetBox
   kept, said), committed as you with `Retired-Device:`, `Reason:`, one `Retire-Step:`
   trailer per step to do, its rollback block (`Rollback-Block:`, masked) and one
   `Not-Done:` trailer per thing deliberately kept. Only those paths are staged. Every file
   stays in history. The post-commit hooks then push the commit to the remote. A failed
   commit puts the tree back.
6. **Its golden tags** (`tags`). Read: the repository's tags `golden/<device>/*`. Sent:
   nothing. Recorded: each archived as `retired/<device>/<identity>/<time>`, an annotated tag
   on the same commit carrying the old one's message and where it came from, then the old
   name deleted; the archived tags are pushed. A restore point at or before the device's
   retirement is never offered to a device of the same name, whatever its tag is called
   (the remote keeps its copies of the old names: a push deletes no tag), and a baseline
   holding the old device's golden is not its restore point either.
7. **Its rollback block** (`rolled_back`). Read: the record of rolled-back changes. Sent:
   nothing. Recorded: the block cleared, after the retire commit archived it (a run finishing
   after the commit records it in a commit of its own first): it survives there, masked.
8. **Its queued items** (`approvals`). Read: the approval queue. Sent: nothing. Recorded:
   each pending item for the device (by its name or any address it was known by) withdrawn,
   kept in the queue with "retire" and your reason, so an item for a new device at its
   address is queued again.
9. **Its rotation policies** (`rotation_policy`). Read: the credential-rotation policies.
   Sent: nothing. Recorded: its name taken out of each policy's device list, as a settings
   write as you, each change recorded with the credential changes. A policy naming only this
   device is turned off: a policy naming no device covers every device its profile covers,
   so removing the name alone would widen it. While another network has a device of the
   same name the policies keep the name, and the preview says so.
10. **Its Topology entries** (`topology`). Read: the Topology's expected islands and the
    arranged layout. Sent: nothing. Recorded: its expected-island declaration withdrawn and
    its place on the arranged map removed, each in the Topology's own log, which History
    reads.
11. **Its heartbeat rule** (`heartbeat`). Read: the generated heartbeat rules (the file
    written for installing, else the one Grafana loads), and Grafana's own rules. Sent:
    nothing. Recorded: the rules file written without the device's rule where a re-measure
    writes it, with who and why beside the re-measures, and a delete file beside it naming the
    rule (Grafana keeps a rule its file dropped unless a file names it for deletion, C1419);
    the result names the one host step that installs both and proves the rule gone. Until then
    the hourly check names the rule EXTRA. When no rules file names the device but Grafana
    still runs its rule, the delete file alone is the work. The only rule in the file is not
    removed (a file with no rules reads like a healthy fleet), and the preview says so.
12. **Its telemetry rules** (`telemetry`). Read: the generated telemetry rules (the file
    written for installing, else the one Grafana loads), and Grafana's own rules. Sent:
    nothing. Recorded: the rules file written without the device's rules (one per
    subscription), and a delete file beside it naming them (C1419); the result names the host
    step that installs both, `c1419-install-alert-rules.sh telemetry`. When no rules file names
    the device but Grafana still runs its rules, the delete file alone is the work. When the
    device's rules are the file's only rules, the file is not written without them (the
    generator never writes an empty population), and the preview says so.
13. **Its console path and console runs** (`console`). Read: the device's console path in
    NetBox, the tool's created-object record, and out-of-band ZTP's console ZTP index and
    runs (its console surveys and kick-starts). Sent: nothing to the device; to
    NetBox, with writes allowed, the device's console port and the cable on it deleted, each
    only where the tool created it (tagged `nmas-managed` AND recorded as created). A port or
    cable a person made is kept and the preview says so. The console server's port, and the
    tool's record of how to reach it, are kept: they are the console server's, and serve the
    next device cabled to it. Recorded: the device's console survey and kick-start records
    moved aside to `console_ztp/retired/` (kept, read by no current reader) and its entries
    removed from the console ZTP index, so no survey of the retired device stands for a new
    device of the same name.
14. **Its NetBox record** (`netbox_record`). Read: Mercury's created-object record and the
    NetBox device. Sent: nothing to the device; to NetBox, with writes allowed, the record
    set to Decommissioning and renamed `<device>-retired-<id>` through the tool's write gate,
    its before recorded, then read back. NetBox keeps a device's name unique in its site and
    tenant, so the rename is what frees the name: onboarding a new device of the name then
    creates a NEW record, and never matches the retired one (by name, or by a serial it
    reports). Its IP addresses leave it too, so a new device given the same address can be
    given it in NetBox: the record's primary addresses are cleared in the same write, each
    address the tool created (tagged `nmas-managed` and in its created-object record) is
    deleted, and every other one is unassigned and kept, its before recorded; the preview names
    each address and which it will be, and the read-back checks the record holds none.
    Recorded: Mercury's created-object entry marked retired, kept with its id and
    never matched by name again. With NetBox writes off, the record is not changed and the
    preview says so: the name stays taken in NetBox until it is renamed there, and its
    addresses stay assigned to it.
15. **The legacy file** (`legacy`). Read: the deprecated `golden_configs/` store and the
    repository. Sent: nothing. Recorded: the device's legacy file deleted, only when its
    content survives in the repository (the migration's verbatim backup or an equivalent
    committed golden), and the step says where. A file whose lines exist nowhere else is
    kept and named.
16. **The SSH host key** (`host_key`). Read: the tool's record of SSH host keys, and every
    network's inventory and onboarding record. Sent: nothing. Recorded: the key the tool kept
    for the device's address (see [Re-key](rekey#every-session)) is forgotten: it moves into
    the record's history with when, who and why ("r5 retired by you: your reason"), and the
    next machine to answer at that address is a first contact, its key kept as the first one
    was. The preview names the key, by its fingerprint, and the apply forgets only that key.
    When another device in any network has the same address, the key is still that device's:
    it is KEPT, and the preview says so naming both devices. Before the row, so a run that
    stops here can be run again.
17. **The inventory row** (`row`). Read: the break-glass basis again. Sent: nothing.
    Recorded: the device's row deleted from the list's inventory. LAST, and only against a
    break-glass record holding this device's current credential, because the row is the
    only stored copy. Deleting it also tells the app's Prometheus target keeper the
    inventory changed, so the generated scrape files drop the device where the app writes
    them.

Nothing is sent to the device at any step.

## What a new device of the same name sees {#same-name}

The records the tool keeps by a device's NAME count only what came after the name's newest
retirement: its restore points (and no baseline holding the old device's golden), its deploy
and restore receipts (Needs attention's rows, a preview's earlier authorisations), and its
credential's age for rotation. The retired device's receipts stay in the record, and History
draws them.

## What retiring does not do

Each is correct, and each is named in the commit and on the screen so it is not mistaken
for an omission:

- The NetBox device is kept: NetBox records what exists, not what the tool manages. It is set
  to Decommissioning and renamed (writes allowed); if the tool created it, Remove could still
  delete it, as a separate decision.
- A template approval is not withdrawn: an approval is of the template, never of its
  devices.
- What still watches it is said in two kinds, below.
- Its running configuration is not changed.
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
- Its Grafana heartbeat rule: retiring removes it from the generated rules file (step 11)
  and names it in a delete file beside it. Grafana keeps a rule its file has dropped unless a
  file names it for deletion, so the host step (`c1419-install-alert-rules.sh heartbeat`)
  installs both, restarts Grafana, proves the rule gone and every other rule running, and
  removes the delete file. When no rules file names the device but Grafana still runs its
  rule, the step names it for deletion alone. The hourly check names it EXTRA until then.
- Its Grafana telemetry rules, one per subscription: retiring removes them from the generated
  telemetry rules file (step 12) and names them in its delete file, and the host step
  (`c1419-install-alert-rules.sh telemetry`) installs both; the hourly telemetry check names
  them EXTRA until then.

**What survives**, each with how it is removed:

- The NetBox device, set to Decommissioning and renamed, its credential masked: delete it in
  NetBox if it is gone for good.
- A Grafana dashboard panel built by hand that names it: removed in Grafana by hand; the tool
  does not edit dashboards.
- A template's approval: it stays, because an approval is of the template. Only a template
  approved now is listed; a revoked one has no approval to keep.
- The SSH host key the tool kept for its address, only when another device in any network
  has that address: it is still that device's key.
- Its credential, only in the break-glass record. Managing it again is onboarding or adopt,
  not an undo.

**Its address afterwards.** The device has no device page once retired: its address shows
its retired record instead, read from the retire commit (who retired it, the reason, the
commit, when). **Its history (the same timeline, filtered to <device>)** opens History
filtered to it, and **Onboard it again…** opens onboarding's form in place with the name
filled in: managing it again is a new onboarding, not an undo.

## Two ways in, two kinds of evidence

The Device page's Retire trusts the break-glass EXPORT LOG, because it cannot reach a file
on your laptop, and says so: the log records what an export wrote, and cannot show the file
still exists or that its passphrase is known. The command on the host (`nmas-retire`) opens
the record itself, with the passphrase you type, and refuses unless the record holds this
device's current username and password for this list.
