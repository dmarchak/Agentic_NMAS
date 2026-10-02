# Restore and re-apply a baseline

A restore sends a device back toward an earlier recorded moment: one device's golden, or a
whole baseline across the devices you choose. It is a deploy whose target is the past
instead of intent, and it runs through the same pipeline.

## The preview

1. **Choose the moment and the scope.** A device's restore points are its golden now, its own
   golden tags, and the baselines that hold it. A baseline's re-apply starts with no device
   ticked; you choose which.
2. **For each device, the program is computed** against its committed golden: the lines the
   chosen moment had and the device lacks. It is ADDITIVE: residue (lines the device has and
   the moment lacked) is listed and NOT removed.
3. **Credentials stay current.** A line that would change an account the device holds now is
   refused, and a credential or community the moment had and the device no longer has is held
   back until you authorise it with a reason. A baseline older than a rotation would otherwise
   put back a password the rotation retired.
4. **Intent goes with the device.** The moment's intent for that device is re-committed in the
   same commit as its new golden, so the next deploy does not offer to undo the restore.

## The run

The pipeline's stages run as for a deploy: `netbox_query`, `template_render`, `ci_gate`,
`pre_snapshot`, `config_diff`, `deploy`, `post_snapshot`, `verify`, `save_golden` and
`audit_log`. Verify checks what the moment's intent declares, so a protocol the restore was
meant to bring back is checked, not assumed.

## The baseline the restore earns

A restore earns a new baseline only if EVERY device in the network is measured equivalent to
the chosen moment afterwards, however it got there. Residue denies it: a merge cannot remove
a line, so the network is not at that moment while residue remains.

## A withdrawn baseline

A baseline someone withdrew (it recorded a broken state) is refused wherever it is read, and
drawn with the reason it was withdrawn.
