# Onboard devices: Discovered

The devices asking for an address on the ZTP segment that the tool does not know: no
reservation names them, and no onboarding waits for them. Reach it from Devices (Discovered).
The page names its network (`/v2/onboard/discovered?list=<network>`) and draws what the
discovery reader last read from Kea; it never asks Kea while you look. The reader reads every
30 seconds, and the page redraws by itself when a device asks anew. Its two tabs are **Plan
devices** (the Devices page) and **Discovered (N)**.

When there is nothing to draw it says why instead: the discovery reader has not read Kea yet
(and why its last attempt failed, if it did); its store cannot be read, so nothing is drawn
rather than a list that may be wrong; or there is no DHCP server to read here (Settings ›
Integrations › Kea).

## What it is for {#what-it-is-for}

Onboarding a device nobody typed a MAC for. A device that boots with no configuration asks for
an address. If no reservation names it, Kea gives it one from the **discovery range**: a
five-minute lease with no boot file, router or DNS, so it reaches nothing and phones no one.
It appears here, and nothing happens to it until a person picks it. See
[Onboard a device](onboard).

## The discovery range {#range}

Two pools in the ZTP subnet, added once by a host step. The first is
for a device sending vendor class `ciscopnp` (option 60), the second for the rest, so the pool a
lease came from says the device's vendor class. Kea only gives these addresses to the ZTP
subnet's own clients: a device with no reservation, asking directly on the ZTP segment rather
than through a relay. Kea's client classes apply everywhere, and their five-minute lease would
otherwise cut every unreserved client's lease in every subnet (measured). If Kea runs no
discovery range, or only part of one, the page says so first.

## The groups {#groups}

The counts lead. **Asking now** (a request in the last ten minutes) is open. **Picked, not
taken** opens when it has rows; **Gone quiet** is collapsed. Above them, **not listed** counts the MACs Kea already
reserves and the onboardings waiting with a MAC: those are never discovered devices. The vendor
buttons and the search (MAC, client-id or hostname) narrow every group. The page says when it
shows a subset, and **Show all** clears it.

- **Asking now:** each device's MAC, vendor class, client-id (option 61), hostname if it sent
  one, the address of its discovery lease, when it was first seen and when it last asked.
  **Next request** is the device's own cadence, read from the gaps between its requests, never
  a number written into the tool. A device seen once says its cadence is not known yet.
- **Picked, not taken:** a MAC Kea now reserves, still on its discovery lease. Measured on a
  C8000v: a device asking for over an hour before its Pick may never take it. It must be
  restarted: it asks again as it boots and takes the Pick. v2 has no control that restarts a
  device it has not onboarded, nor one that declares a planned restart beforehand (a gap,
  registered, C1361), so that restart is done outside the tool.
- **Gone quiet:** no request for over ten minutes. It is listed for 24 hours after its last
  request, then dropped. A C8000v never gives up on its own, so a quiet one was most likely
  switched off or given a configuration at its console.

## Pick {#pick}

**Pick…** opens Add device in place, with the MAC the device asked with and the ZTP way chosen:
the tool reserves the device by that MAC and serves its first configuration. Name it, check its
platform, role and management address, then review the plan and create it, as in
[Onboard a device](onboard). Nothing is reserved until you create it.

## What it does not do {#not}

It never picks a device by itself, and never by serial: on a virtual C8000v the board serial
changes at every boot and the licence serial is shared by every one. Any input at a device's
console ends its discovery.
