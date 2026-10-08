# Run a privileged command (Tier 2)

Some exec commands change a device's state, and the device rebuilds that state by itself: its
counters count again, ARP relearns, its log buffer fills. These are Tier 2 of the command policy
([the command policy](show-commands#tiers)). They do not run from Show commands or Ask the
device. Each is this operation, one device at a time, from the device page's **Actions** menu:
**Run a privileged command…**. The agent never runs one.

![Run a privileged command: the plan refuses a command that is not offered or not yet measured, an interface the device's committed golden does not hold, or the one carrying the address Mercury reaches it on, before anything is read; the preview reads the before-state through the reads engine, recorded; you confirm with a reason, bound to the plan; holding the device, the before-state is read again and kept, the command is sent once and only its measured prompt is answered; the after-state is read back and judged; the run is recorded, and History shows it. Rollback does not apply.](diagrams/privileged.svg)

## The commands

| Command | On | It asks | Verified by |
|---|---|---|---|
| `clear counters` | one interface | `Clear "show interface" counters on this interface [confirm]` | `Last clearing of "show interface" counters` reading under a minute |
| `clear arp-cache` | one interface | nothing | the interface's ARP entries back (read up to 3 seconds) |
| `clear logging` | the device | `Clear logging buffer [confirm]` | the buffer emptied (its "messages logged" count is not reset) |
| `undebug all` | the device | nothing | `show debugging` reading as nothing on |
| `clear ip bgp <peer> soft` | a peer | not measured yet | not offered until it is |

Each prompt was measured on both platforms (IOS-XE and IOS) before this was built. The
interfaces offered are the device's own, from its committed golden; the one carrying the address
Mercury reaches it on is never offered.

## The steps

1. `refuse`: the plan refuses, naming why, before anything is read: a command not offered, one
   not yet measured, an interface the device's golden does not hold, or the management one.
2. `read`: the preview reads the before-state through the reads engine (a recorded run) and
   draws it, with what the command affects, what it will not do, and why rollback does not
   apply. `undebug all` with nothing on says it changes nothing.
3. `confirm`: you give a reason of three words or more and confirm. The confirm is bound to the
   plan: if the device's address or the command moved, nothing is sent.
4. `send`: holding the device, the before-state is read again and kept in the record (the
   counters, the log buffer: these commands destroy evidence), masked and capped. The command
   is sent once. Only its measured prompt is answered, with Enter; any other question is not
   answered and the session is closed, which abandons the command.
5. `verify`: the after-state is read back and judged by the measured rule above. A read Mercury
   cannot judge says "not verified", never "done".
6. `record`: the run is written, with who, when, why, the kept before-state, what the device
   printed and the verdict. History shows it under Privileged commands.

Rollback does not apply: what these commands clear cannot be put back.
