# A path trace: the path packets take

Topology's **Path…** answers "which way does traffic from this device to that address go?" from
the devices themselves: each routed hop is asked its own forwarding answer for the destination,
and that answer decides which device is asked next. It changes nothing on any device.

![A path trace: From and To are checked before any device is asked; the first device is asked show ip cef for the destination through the reads engine, held while read and recorded; each next hop its answer names is followed to the device holding that address, which is read next, equal-cost next hops branching; a branch stops when the packet is delivered, dropped, not readable, in a loop, leaves the network, or reaches a bound; the trace is recorded with each read, and Topology draws it.](diagrams/path-trace.svg)

## The steps

1. `refuse`: From must be a device of the network that takes part in routing, and To one IPv4
   address. Anything else is refused, naming what was compared and both sides (an IPv6 To says
   the trace reads IPv4 forwarding only); no device is asked and nothing is recorded.
   **Trace the path** needs a verified person, because each answer is shown to the person who asked.
2. `read`: each device is asked `show ip cef <destination>`, its one field the address, through
   the reads engine: held while read (a device another operation holds is not read, and says
   who holds it), masked, recorded on History › Reads as yours. The devices at one step of the
   trace are read together; each device is read once per trace.
3. `follow`: the answer names the route the device uses and its next hops. Each next hop's
   address is looked up in committed intent, as the topology reader stores it, to find the
   device that holds it; that device is read next. Equal-cost next hops each start a branch.
   An address two devices hold is not attributed to either.
4. `stop`: a branch ends, saying why, when the destination is reached (the device holds the
   address, or has it attached), when a device has no route or discards it, when a device
   cannot be read (what follows is not known, never guessed), at a forwarding loop, when the
   next hop is a device outside the network that is not the destination (where the network's
   knowledge ends), or past 8 branches or 16 hops.
5. `record`: the trace is written as it starts and after each step: who, when, From, To, which
   devices are being read, each branch and its hops, and the reads it made. Topology draws it
   from that record, so it reads the same later and in another tab; the latest 50 traces of a
   network are kept, and the reads themselves for the network's read retention.

## What it does not read

Layer 2. Between two routed hops the map draws the cabling's path through switches, dashed, and
the card says "layer 2, not read": which switches a frame crosses is the switches' forwarding,
which the trace does not ask. A trace reads IPv4 forwarding only.

## Why a branch can drop while traffic still flows

A device chooses among equal-cost next hops per flow. When one branch is delivered and another
drops, the flows hashed to the dropping branch are lost while the others arrive: the trace shows
both, so a partial failure is not drawn as a working path.
