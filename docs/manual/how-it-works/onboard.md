# Onboard a device

Onboarding brings a NEW device into the tool: it gives the device a configuration to boot
with, then reaches it, takes ownership of its credential and records it. A device the tool
did not build is adopted instead (see [Adopt a device](adopt)).

![The onboarding flow: Create stages a credential and commits a bootstrap with nothing sent; the device boots on that bootstrap config (static, DHCP, or served by the tool through ZTP); Verify reaches it, rotates its credential, saves it and records its first golden, then promotes it; seeding and deploys follow.](diagrams/onboarding-flow.svg)

## Phase one: Create (nothing is sent to any device)

You choose the device's name, platform, role and how it gets its address: static, a DHCP
reservation, or ZTP (the tool serves its configuration on first boot). The plan refuses at
once anything that would fail later, every reason together. Then, in order:

1. `credentials`: a one-time bootstrap credential is generated and staged, so it survives a
   crash.
2. `commit`: the device is committed to the network's repository with its bootstrap intent,
   and named in the manifest. It is now PENDING: known to the tool, not in the inventory.
3. `reserve` (ZTP only): the DHCP reservation is written to Kea, tested before it replaces
   the live file. It is last among the steps that can fail, because it is what the device
   will see.
4. `render`: the bootstrap configuration is rendered, ready to download (or to be served by
   ZTP). It carries the bootstrap credential and only what the device needs to be reached.

## Between the phases: the device boots

The device boots on its bootstrap configuration. A pending device can be abandoned at any
time: nothing has reached it yet, so abandoning removes only what the tool wrote.

## Phase two: Verify

Verify reaches the device, which is the only proof its address and management interface are
right. It previews what it will send (the monitoring profile's lines, the RW community's
removal) and then, holding the device, in order:

1. `verify`: signs in with the staged credential. Three outcomes, each said: it answered; it
   answered and refused the credential; it did not answer (with the likely causes).
2. `capture`: reads the running configuration, held in memory, not yet recorded.
3. `rotate`: replaces the bootstrap credential with a generated one the device hashes,
   verified on a fresh login before it is trusted.
4. `remove_rw`: removes the read-write SNMP community the image arrived with, verbatim.
5. `profile`: sends the network's monitoring profile and reads it back.
6. `persist`: saves the device and reads the startup configuration back.
7. `golden`: reads the device again and commits its FIRST golden, which is therefore a record
   you would want to restore, not the state before the cleanup.
8. `netbox`: records the device in NetBox, if writes are allowed.
9. `promote`: adds the device to the inventory, last, with the rotated credential. Only now
   is it onboarded.

A step that fails stops the run and names every step that did not run; the device stays
pending, and Verify can run again.

## Then

The device has bootstrap intent only. Seed its intent (see [Seed intent](seed)), and from
then on change it by deploys.
