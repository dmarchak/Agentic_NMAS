# Adopt a device

Adoption brings a device the tool did NOT build under management. You supply a working
login; the tool uses it once, adds its own account, and from then on uses only its own.

## The supplied credential is never written

It is somebody else's login. It is held in memory for the operation only, never in a file, a
log or a commit. If adoption fails, its owner still has it, unchanged.

## The preview (it reads, and sends nothing)

1. **Can the tool's account work?** A device whose SSH logins would never consult a local
   account is refused before anything is sent, naming why.
2. **What a reload would lose**: the running configuration against startup.
3. **What NetBox already holds** for the device, and the import's own dry run.
4. **Every credential the golden would carry in a reversible form** is refused by name. Only
   the supplied account may be converted, if you choose it: same password, stored as a hash.

## The apply, in order

Holding the device, and refusing if anything moved since the preview:

1. `confirm`: the preview's fingerprint is checked again.
2. `account`: the tool's own account is added through the supplied login, then proven on a
   fresh login with its own password.
3. `owner_account`: if you chose it, the supplied account is converted to a hashed secret
   with the same password, proven on a fresh login, and put back if that fails.
4. `profile`: the network's monitoring profile is sent and read back.
5. `persist`: the device is saved, and its startup configuration read back.
6. `golden`: the first golden is committed, `Source: adopt`.
7. `netbox`: the device is imported into NetBox; what already existed there is recorded as
   ADOPTED, never as created, so Remove can never delete it.
8. `promote`: the device joins the inventory with the tool's account, last.

A stopped run resumes from the tool's own record.
