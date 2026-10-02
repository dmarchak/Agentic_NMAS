# Remove a line (Mode B)

A deploy never removes anything: it only adds. A line the device has and intent lacks stays
until you remove it deliberately, one unit at a time. That is Mode B.

## What can be chosen

The deploy preview lists the device's residue. Each line, or a whole stanza intent lacks, is
a unit with a box:

- **Ticked**, it will be removed, and asks for your reason (one decision, one control: the
  tick chooses it, the reason says why).
- **Disabled, with the reason beside it**, where removing it is refused: IOS will not remove
  it; it is a numbered ACL entry (removing one deletes the whole list); it is on the path the
  tool reaches the device by; it is an account; a named object still in use refers to it.

## Only measured shapes

`no <line>` can remove more than the line. So a line is removable only if its SHAPE was
measured on its platform, by a probe on a throwaway device, to remove exactly itself and
nothing else. An unmeasured shape is refused, naming the probe that would measure it.

## The run

A removal rides at the end of a deploy's program, through the same pipeline: `netbox_query`,
`template_render`, `ci_gate`, `pre_snapshot`, `config_diff`, `deploy`, `post_snapshot`,
`verify`, `save_golden`, `audit_log`. The negation sent is the device's own line, verbatim,
with `no` in front, inside its section. Verify reads each removed line back to confirm it is
gone, and the undo, if verify fails, puts the device's own lines back as they were (never a
second negation).

## Why it works this way

Converging a device to intent automatically would remove anything somebody added by hand,
including what was keeping the network up. A person chooses each removal, says why, and the
reason is in the receipt.
