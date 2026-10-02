# Remove a line (Mode B)

A deploy adds: it never removes a line the device has and intent lacks (the one delete it
sends itself is re-creating a running IP SLA operation intent changes). Such a line stays until
you remove it deliberately, one unit at a time, with a reason. That is Mode B. It rides on a
deploy, so it changes the device's running and startup configuration, its golden, and the
deploy record.

![Mode B in three bands. In the tool, the deploy preview lists the lines the device has and intent lacks; a person ticks one and gives a reason, and only a shape measured on the platform is allowed. The removal is sent last in the deploy's program, as the device's own line with no in front, and verify reads the device back to see the line gone. If verify fails, the undo puts the device's own line back from the pre-change snapshot.](diagrams/removal.svg)

## What can be chosen

You open the deploy plan for the device (see [Deploy a change](deploy)). Its preview's "What
will NOT happen" part lists the device's residue: every line the device has, by its committed
golden, that intent lacks, under its section, and every stanza whose header intent lacks as
one unit, its lines implied. Each unit has a box, identified by an ID rather than its text,
because the plan is masked and a line in a secret position could never be sent back by its
text. The monitoring profile's Apply offers the same boxes for a device's lines the profile
supersedes, never ticked for you.

- **Ticked**, it will be removed. Ticking plans the device again (the browser posts the ticked
  IDs to `/deploy/plan`), and the line appears at the end of the program with a reason field:
  one decision, one control, so the tick chooses it and the reason says why. Typing the reason
  plans the device again so the hash covers it. A reason must be at least three words and not
  a copy of the line.
- **Disabled, with the reason beside it**, where removing it is refused:
  - IOS will not remove it, or removes it differently: the `hostname`, `version`, the boot
    markers, a `line` stanza, `end`, a banner, a `crypto pki` trustpoint or certificate, a
    physical interface (`default interface` resets one, and that is not built), and
    `logging buffered` (measured: `no logging buffered` turns buffered logging off instead of
    restoring the default);
  - a numbered access-list entry in the global form (`access-list 10 …`), because removing one
    deletes the whole list;
  - the path the tool reaches the device by: the interface holding the management address (or
    an address from DHCP), the vty lines, `ip ssh`, `aaa`, `crypto key`, the domain name, a
    static route, the default gateway;
  - an account (`username`, `enable secret`, `enable password`), which is retiring's or
    rotation's job;
  - a named object something still uses (an access list, prefix list, route map, VRF,
    class map, policy map, key chain or object group), naming the line that uses it;
  - a shape not measured on this platform (below).
  - A `line vty` stanza intent regroups says instead that it merges into intent's stanza once
    its settings are applied, so nothing is removed.

## Only measured shapes

`no <line>` can remove more than the line: `no access-list 10 <entry>` deletes the whole list.
So a line is removable only if it matches a SHAPE that was measured on its platform to remove
exactly itself and nothing else. The record, per platform, is
`modules/nsot/removal_measured.json`, which ships with the program: a new measurement takes
effect with a release. An unmeasured shape is refused, naming the probe run that would measure
it; a shape measured to do more is refused with what was measured; an unreadable record
allows nothing.

The operator measures a shape on the host with `scripts/nmas-removal-probe`, on one device of
each platform, holding the device for the whole run:

1. **Read the starting state.** Read: `show running-config` over SSH. Sent: nothing.
   Recorded: nothing.
2. **Add a scratch instance.** Sent: a scratch line of the shape in configuration mode (names
   starting `NMASPROBE`, documentation addresses, `Loopback199`), then read it back. Recorded:
   nothing. The probe stops if the scratch did not land.
3. **Send Mode B's program.** Sent: exactly the program a removal would send. Read: the
   configuration again. Recorded: the result, by comparison with step 2: `exact` (only the line
   gone), `broader`, `different`, `incomplete`, `overrides_default` or `refused`.
4. **Put the device back.** Sent: the scratch taken away and anything step 3 removed put back.
   Read: the configuration again, which must be equivalent to step 1, or the probe stops and
   says so first. Recorded: nothing on the device; it changes the running configuration only
   and never saves, so a reload also returns the device.

The probe prints its results; they become the record by being committed into the program. A
shape that needs the device's live BGP process runs only when asked for by name.

## The run

You confirm the deploy as usual (**Deploy confirmed devices**). Before the pipeline, the apply
checks that every removal still matches a line on the device's committed golden and carries a
reason of the right shape. The removal then rides at the END of the deploy's program, after the
additions and any re-created IP SLA operations, through the same pipeline (see
[Deploy a change](deploy#the-run-stage-by-stage) for what each stage reads and sends):

1. `netbox_query`. Read: the device's NetBox record, where configured. Sent: nothing.
   Recorded: whether NetBox answered.
2. `template_render`. Read: the confirmed program, removals included. Sent: nothing. Recorded:
   nothing.
3. `ci_gate`. Read: the program. Sent: nothing. Recorded: nothing. A removal that matches a
   dangerous pattern (`no ip address`, `no router …`) passes only on its stated reason.
4. `pre_snapshot`. Read: over SSH, the routing, interface and route facts and the running
   configuration. Sent: nothing. Recorded: the pre-change snapshot, which the undo puts lines
   back from.
5. `config_diff`. Read: the program and the running configuration. Sent: nothing. Recorded:
   the counts.
6. `deploy`. Sent: the program in configuration mode over SSH, then `write memory`. Each
   removal is `no` plus the device's own line, verbatim, inside its section; a line that is
   itself a `no` line is removed by its positive form; a stanza is removed by negating its
   header once. Recorded: the push time.
7. `post_snapshot`. Read: the same facts and `show running-config`, on a new SSH session. Sent:
   nothing. Recorded: nothing yet.
8. `verify`. Read: the post-change configuration. Sent: nothing. Recorded: how many removals
   were checked and any still present, for the receipt. Each removed line must read back gone;
   one still there fails verify and starts the rollback. A configuration that could not be read
   makes verify not pass, without a rollback.
9. `save_golden`. Read: the post-change configuration. Sent: nothing. Recorded: the capture,
   handed to the batch's one golden commit.
10. `audit_log`. Recorded: the run's audit entry, as for any deploy.

If verify fails, the undo puts the device's own removed lines back as they were, taken from the
pre-change snapshot and only those still missing, each checked to be a line the snapshot held:
never a second negation. The rolled-back block records the additions only, and the removal's
box shows next time that it was rolled back, when and why. The receipt records each removal by
its ID, its line (masked) and your reason.

## What a removal does not do {#what-a-removal-does-not-do}

- It never converges a device to intent: nothing is removed that you did not tick.
- It is offered only on a deploy: a restore and a capture remove nothing.
- It never restores a default (`default <command>` is not built), and never removes an account
  or the management path.

## Why it works this way

Converging a device to intent automatically would remove anything somebody added by hand,
including what was keeping the network up. A person chooses each removal, says why, and the
reason is in the receipt.
