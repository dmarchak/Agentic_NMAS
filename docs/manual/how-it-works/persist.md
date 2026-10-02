# Persist

A device boots from its startup configuration, not from what it runs now. Persist saves the
running configuration to startup and proves it was saved, so a reload brings the device back
as it is, with the credential the tool holds.

## The preview

The preview contacts no device. It shows what will happen and the hourly startup check's
last reading for the device, with its age.

## The apply, in order

1. **Save**: the device's own save (`write memory`), on a session that holds the device.
2. **Read back**: the startup configuration is read back. The device is persisted only if
   the startup configuration carries every `username` line the running configuration has,
   verbatim.
3. **Record**: the outcome is recorded, as you, where job health reads it, so the "would boot
   the wrong credential" row clears only on a read-back that matched.

## What persist does not do

It changes no configuration: the save carries the running configuration exactly as it is,
including anything not yet recorded as a golden.
