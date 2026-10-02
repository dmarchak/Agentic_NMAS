# Rotate a credential

Rotation replaces the password the tool uses to sign in to a device, and makes sure the tool
never loses access while it does. It is the riskiest operation in the tool, so every state
between "the device changed" and "the tool holds the new password" is named and recoverable.

## The preview

1. **The account's line is read live** from the device, because the program depends on
   whether the device holds a `secret` or a `password` now, not in a stored capture.
2. **The program is shown** with the new password masked.
3. **Preflight checks** are drawn by name; any one failing refuses the rotation before
   anything changes.

## The apply

The apply runs as a job, holding the device from start to finish, so no other operation can
touch it meanwhile:

1. **The new password is staged** on the host first, so it is never lost if anything after
   this fails.
2. **The new account line is sent** on a held session.
3. **The new password is tried on a fresh login.** Only if that works does the rotation
   continue; if it does not, the old line is put back on the held session and proven.
4. **The new password is recorded** where the tool reads it. Only then is the staged copy
   cleared.
5. **The device is persisted** (see [Persist](persist)): saved, and its startup
   configuration read back, so a reload does not bring back the old password.

## The outcomes

The result names one state, with its next step: rotated and persisted; rotated but not yet
persisted; rotated and not recorded (the staged copy is the only one, and the recovery
command is named); reverted; or failed before any change.

## After a rotation

The break-glass record holds the old password, so the result's next step is a new
break-glass export.
